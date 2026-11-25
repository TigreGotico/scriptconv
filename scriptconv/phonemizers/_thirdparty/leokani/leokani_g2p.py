#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Leokani G2P by Milliwatt Labs (milliwattlabs.com)
"""Leokani G2P: English text to Kokoro-style phonemes, without espeak-ng.

One clause ("piece": words with no punctuation between them) in, the phoneme string Leokani-tts reads out, with
stress marks. It produces espeak compatible phoneme codes, made from the ground up: the same Kokoro/misaki-style
codes Leokani-tts and Kokoro use. It contains no espeak-ng code or data files.

    python leokani_g2p.py "the wind was cold"          # one piece -> phonemes
    python leokani_g2p.py --text "Hello there, Sam."    # a whole line (pieces + punctuation), as leokani.py does

    from leokani_g2p import LeokaniG2P
    g2p = LeokaniG2P()
    g2p.phonemize("Dr. Okafor lands at 7:45 AM.")         # a whole line -> one phoneme string
    g2p.phonemize_chunks("A long paragraph. Of text.")      # -> one phoneme string per clause chunk

How it works, per piece:
  1. Each word gets a base pronunciation: the lexicon (leokani-g2p.data and leokani-g2p-words.data), else the number
     reader for digits, else the letter-to-sound model (oov-encoder.onnx + oov-decoder.onnx, greedy).
  2. The context model (context.onnx) looks at the whole piece and picks, per word, how the base is said here
     (a stress change or a weak form such as "to" -> tə), the word edge (a flap, a linking ɹ), and whether the
     word is written together with the next one ("in the" -> ɪnðə).
Needs numpy and onnxruntime. Leokani G2P by Milliwatt Labs (milliwattlabs.com): this code is MIT; the weights,
lexicon and goldens are CC BY 4.0 (see LICENSE and NOTICE).
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import re
import sys
import unicodedata

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
FORMAT = "leokani-g2p/1"
# Model files. 1.3: leokani-g2p.data holds the tables and the common words, leokani-g2p-words.data the other words
# (read on first use). 1.0-1.2 had one leokani-g2p.json.gz; both layouts load.
DATA_FILE, WORDS_FILE, JSON_FILE = "leokani-g2p.data", "leokani-g2p-words.data", "leokani-g2p.json.gz"
ONNX_FILES = {"enc": "oov-encoder.onnx", "dec": "oov-decoder.onnx", "ctx": "context.onnx"}
DATA_MAGIC = b"LKG2P13\x01"
# Model variants by name: the folder relative to the release folder. micro (2.2 M letter-to-sound parameters) is
# the default and sits at the top; mini (2.9 M, better on unknown words and names) is in mini/.
VARIANTS = {"micro": "", "mini": "mini"}
DEFAULT_VARIANT = "micro"


def variant_dir(directory: str = HERE, variant: str | None = None) -> str:
    """The folder holding VARIANT's model files under a release folder (variant None or "micro": the folder)."""
    v = variant or DEFAULT_VARIANT
    if v not in VARIANTS:
        raise ValueError(f"unknown Leokani G2P variant {v!r} (have {', '.join(VARIANTS)})")
    return os.path.join(directory, VARIANTS[v]) if VARIANTS[v] else directory

PRIMARY, SECONDARY = "ˈ", "ˌ"
VOWELS = set("aeiouæɑɐɒɔəɛɜɪʊʌAEIOUWYᵊᵻɚɝ")
# context model output slots: generic stress edits of the base, then the word's own variants from the lexicon
STRESS_OPS = ("same", "demote", "strip", "promote1", "demote1", "demoteLast", "promote")
N_VARIANTS = 6
EDGE_OPS = ("none", "flap", "linkr", "unflap")
CTX_FEATURES = ("word", "shape", "first", "last", "last2", "nprim", "nsec", "nvow", "ntok", "src", "isfirst",
                "islast", "fromstart", "toend")
SRC = ("lexicon", "oov", "number", "symbol", "empty")
SHAPES = ("lower", "title", "caps", "mixed", "digit", "other")


# ---------------------------------------------------------------- stress and phoneme edits

def stress_op(b: str, op: str) -> str:
    if op == "same":
        return b
    if op == "demote":
        return b.replace(PRIMARY, SECONDARY)
    if op == "strip":
        return b.replace(PRIMARY, "").replace(SECONDARY, "")
    if op == "promote1":
        i = b.find(SECONDARY)
        return b if i < 0 else b[:i] + PRIMARY + b[i + 1:]
    if op == "demote1":
        i = b.find(PRIMARY)
        return b if i < 0 else b[:i] + SECONDARY + b[i + 1:]
    if op == "demoteLast":
        i = b.rfind(PRIMARY)
        return b if i < 0 else b[:i] + SECONDARY + b[i + 1:]
    if op == "promote":
        return b.replace(SECONDARY, PRIMARY)
    raise ValueError(op)


def edge_op(s: str, op: str) -> str:
    if op == "none" or not s:
        return s
    if op == "flap":
        return s[:-1] + "ɾ" if s.endswith("t") else s
    if op == "linkr":
        return s + "ɹ"
    if op == "unflap":
        return s[:-1] + "t" if s.endswith("ɾ") else s
    raise ValueError(op)


def candidates(base: str, variants: list[str]) -> list[str | None]:
    """The context model's slots for one word: STRESS_OPS of the base, then up to N_VARIANTS lexicon variants
    (None where a word has fewer)."""
    out: list[str | None] = [stress_op(base, op) for op in STRESS_OPS]
    out += [variants[i] if i < len(variants) else None for i in range(N_VARIANTS)]
    return out


def shape(w: str) -> str:
    if any(c.isdigit() for c in w):
        return "digit"
    if not any(c.isalpha() for c in w):
        return "other"
    if w == w.lower():
        return "lower"
    if w.isupper():
        return "caps"
    if w[0].isupper() and w[1:] == w[1:].lower():
        return "title"
    return "mixed"


def bucket(n: int, top: int) -> int:
    return min(n, top)


def features(words: list[str], bases: list[str], srcs: list[str], word_ids: dict[str, int],
             sym_ids: dict[str, int]) -> np.ndarray:
    """(len(words), len(CTX_FEATURES)) int64 features of a piece for the context model."""
    n = len(words)
    out = np.zeros((n, len(CTX_FEATURES)), dtype=np.int64)
    for i, (w, b, s) in enumerate(zip(words, bases, srcs)):
        bb = b.replace(PRIMARY, "").replace(SECONDARY, "").replace(" ", "")
        out[i] = (
            word_ids.get(w.lower(), 1),
            SHAPES.index(shape(w)),
            sym_ids.get(bb[:1], 1) if bb else 0,
            sym_ids.get(bb[-1:], 1) if bb else 0,
            sym_ids.get(bb[-2:-1], 1) if len(bb) > 1 else 0,
            bucket(b.count(PRIMARY), 3),
            bucket(b.count(SECONDARY), 3),
            bucket(sum(c in VOWELS for c in bb), 7),
            bucket(b.count(" ") + 1 if b else 0, 3),
            SRC.index(s),
            int(i == 0),
            int(i == n - 1),
            bucket(i, 7),
            bucket(n - 1 - i, 7),
        )
    return out


def pick(logits: np.ndarray, cands: list[str | None]) -> str | None:
    """The best (slot, edge) pair the word has: logits over len(cands) * len(EDGE_OPS), slot-major."""
    for j in np.argsort(-logits, kind="stable"):
        k, e = divmod(int(j), len(EDGE_OPS))
        if cands[k] is not None:
            return edge_op(cands[k], EDGE_OPS[e])
    return None


def targets(base: str, variants: list[str], ctx: str) -> list[int]:
    """Every (slot, edge) pair index that turns base into ctx (the context model's any-correct target)."""
    out = []
    for k, c in enumerate(candidates(base, variants)):
        if c is None:
            continue
        for e, eop in enumerate(EDGE_OPS):
            if edge_op(c, eop) == ctx:
                out.append(k * len(EDGE_OPS) + e)
    return out


def assemble(forms: list[str], joins: list[bool]) -> str:
    out = ""
    for i, f in enumerate(forms):
        if not f:
            continue
        if out and not out.endswith(" ") and not (i > 0 and joins[i - 1] and forms[i - 1]):
            out += " "
        out += f
    return out.strip()


# ---------------------------------------------------------------- numbers (espeak's English reading)

class Numbers:
    """Digits read the way the espeak front end reads them: "740" -> sˈɛvənhˈʌndɹɪd fˈɔɹɾi, "$3.50" -> dˈɑləɹ θɹˈi
    pYnt fˈIv zˈiəɹO, "9:05" -> nˈIn zˈiəɹO fˈIv. Atoms (0-99, scale words, signs, letters, ordinals) come from the
    lexicon file. say() returns None for a token it has no rule for."""

    SEG = re.compile(r"\d+(?:,\d{3})*(?:\.\d+)?|[A-Za-z]+|.")
    ORD = ("st", "nd", "rd", "th")

    def __init__(self, atoms: dict[str, str], word=None):
        self.a = atoms
        self.word = word or (lambda w: None)

    def group(self, n: int, pre: bool = False) -> list[str]:
        """0 < n < 1000 -> tokens; pre: the form before a scale word (espeak drops 17's second stress there)."""
        h, r = divmod(n, 100)
        out = [self.a[str(h)] + self.a["hundred"]] if h else []
        if r:
            out.append(self.a[f"pre:{r}"] if pre and f"pre:{r}" in self.a else self.a[str(r)])
        return out

    def integer(self, digits: str) -> list[str] | None:
        n = int(digits)
        if n >= 10 ** 12:
            return None
        if n == 0:
            return [self.a["0"]]
        if 1900 <= n <= 1999 and len(digits) == 4:
            return [self.a["19"] + self.a["hundred"]] + ([self.a[str(n % 100)]] if n % 100 else [])
        out = []
        for scale, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (10 ** 3, "thousand")):
            q, n = divmod(n, scale)
            if q:
                out += self.group(q, pre=True)
                out.append(self.a[name])
        if n:
            out += self.group(n)
        return out

    def digits(self, d: str) -> list[str]:
        """A run with leading zeros: up to 3 digits are the zeros (joined) then the rest as a number; 4 digits are
        one joined run; longer runs are joined digit groups of 3 from the right."""
        if len(d) <= 3:
            z = len(d) - len(d.lstrip("0"))
            z = min(z, len(d) - 1)
            return ["".join(self.a["0"] for _ in range(z))] + self.integer(d[z:])
        if len(d) == 4:
            return ["".join(self.a[c] for c in d)]
        groups, rest = [], d
        while rest:
            groups.insert(0, rest[-3:])
            rest = rest[:-3]
        return ["".join(self.a[c] for c in g) for g in groups]

    def number(self, s: str) -> list[str] | None:
        whole, _, frac = s.partition(".")
        digits = whole.replace(",", "")
        if len(digits) > 1 and digits.startswith("0") and "," not in whole:
            out = self.digits(digits)
        else:
            out = self.integer(digits)
        if out is None:
            return None
        if frac:
            out = out + [self.a["."]] + [self.a[c] for c in frac]
        return out

    SUFFIX_SOUND = {"st": "st", "nd": "ənd", "rd": "d", "th": "θ"}

    @staticmethod
    def right_suffix(n: int) -> str:
        return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")

    def ordinal(self, n: int, suffix: str) -> list[str]:
        """espeak says the ordinal's stem and then the suffix as written: 22nd sˈɛkənd, 22st sˈɛkst, 7nd
        sˈɛvənənd. A whole hundred (100th) is the number and a lone θ."""
        r = n % 100
        if not r:
            return (self.integer(str(n)) or []) + [self.a["ord:th"]]
        head = self.integer(str(n - r)) if n - r else []
        whole = self.a[f"ord:{r}"]
        right = self.SUFFIX_SOUND[self.right_suffix(r)]
        if not whole.endswith(right):
            return (head or []) + [whole]
        return (head or []) + [whole[: -len(right)] + self.SUFFIX_SOUND[suffix]]

    def letters(self, run: str, first: bool) -> list[str] | None:
        """Spelled: every letter's name with secondary stress but the last (a lone leading "a" or "A" is ˌA)."""
        names = [self.a.get("letter:" + c.lower()) for c in run]
        if any(n is None for n in names):
            return None
        spelled = "".join(n.replace(PRIMARY, SECONDARY) for n in names[:-1])
        tail = names[-1].replace(PRIMARY, SECONDARY) if first and run.lower() == "a" else names[-1]
        return [spelled + tail]

    def say(self, w: str) -> str | None:
        try:
            return self._say(w)
        except (KeyError, ValueError):
            return None

    def _say(self, w: str) -> str | None:
        segs = self.SEG.findall(w.replace("−", "-"))
        toks: list[str] = []
        glue = False                       # the next token joins the previous one (after a hyphen)
        i = 0
        while i < len(segs):
            g = segs[i]
            nxt = segs[i + 1] if i + 1 < len(segs) else ""
            prev = segs[i - 1] if i else ""
            if g[0].isdigit():
                if prev == ":" and len(g) == 2 and g.startswith("0"):
                    part = [self.a[c] for c in g]
                elif nxt == ":" and g.isdigit():
                    part = self.integer(g)
                elif nxt in self.ORD and "." not in g:
                    part = self.ordinal(int(g.replace(",", "")), nxt)
                    i += 1
                elif nxt == "s" and "." not in g:
                    part = self.number(g)
                    if part is None:
                        return None
                    part = part + [self.a["suffix:s"]]
                    i += 1
                else:
                    part = self.number(g)
                if part is None:
                    return None
                if glue and toks:
                    toks[-1] += part[0]
                    part = part[1:]
                toks += part
                glue = False
            elif g.isalpha():
                if prev == "-" and len(g) > 1:
                    y = self.word(g)
                    part = None if y is None else [y]
                elif len(g) > 1 and g.islower() and self.word(g) is not None and (nxt == "-" or not prev):
                    part = [self.word(g)]
                elif len(g) > 3 and self.word(g) is not None:
                    part = [self.word(g)]                # COVID-19: a word, not spelled
                elif len(g) <= 3 or g.isupper():
                    part = self.letters(g, first=not toks)
                else:
                    part = None
                if part is None:
                    return None
                if glue and toks:
                    toks[-1] += part[0]
                    part = part[1:]
                toks += part
                glue = False
            elif g in ("'", "’") and nxt == "s" and toks:
                toks.append(self.a["suffix:s"])
                i += 1
            elif g in ("$", "£", "€") and not toks:
                toks.append(self.a[g])
            elif g == "-":
                if not toks and nxt[:1].isdigit():
                    toks.append(self.a["minus"])
                elif toks and nxt[:1].isdigit() and prev.isalpha():
                    toks.append("")                 # espeak: word, an empty item, then the number
                elif toks and nxt[:1].isdigit():
                    toks.append(self.a["-"])
                elif toks and nxt.isalpha():
                    glue = True
                elif not nxt:
                    pass
                else:
                    return None
            elif g in ("%", "°", "/"):
                toks.append(self.a[g])
            elif g == ":":
                if not (len(nxt) == 2 and nxt.isdigit()):
                    toks.append(self.a[":"])
            elif g == "–":
                pass
            else:
                return None
            i += 1
        return self.link(toks) if toks else None

    def link(self, toks: list[str]) -> str:
        """espeak links a word ending in ɚ (əɹ here) to a vowel-initial word with an extra ɹ."""
        out = []
        for i, t in enumerate(toks):
            nxt = toks[i + 1] if i + 1 < len(toks) else ""
            nb = nxt.replace(PRIMARY, "").replace(SECONDARY, "")
            if t.endswith("əɹ") and nb[:1] in VOWELS:
                t += "ɹ"
            out.append(t)
        return " ".join(out)


# ---------------------------------------------------------------- text normalisation (before the lexicon)

PH = ""            # "word" + PH + phonemes: a word whose base is given (the context model still sees "word")

ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
        "seventeen eighteen nineteen").split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()
ORDINAL_WORDS = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
                 "nine": "ninth", "twelve": "twelfth"}


def cardinal(n: int) -> str:
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else "-" + ONES[n % 10])
    for scale, name in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand"), (100, "hundred")):
        if n >= scale:
            q, r = divmod(n, scale)
            return cardinal(q) + " " + name + ("" if r == 0 else " " + cardinal(r))
    raise ValueError(n)


def ordinal(n: int) -> str:
    words = cardinal(n).split(" ")
    head, _, last = words[-1].rpartition("-")
    if last in ORDINAL_WORDS:
        last = ORDINAL_WORDS[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    words[-1] = (head + "-" if head else "") + last
    return " ".join(words)


def plural_number(n: int) -> str:
    """'1990' -> 'nineteen nineties', '80' -> 'eighties', '1800' -> 'eighteen hundreds', '2000' -> 'two thousands'."""
    if 1000 <= n <= 9999 and n % 100 == 0 and n % 1000:
        return cardinal(n // 100) + " hundreds"
    if 1100 <= n <= 1999 or 2010 <= n <= 2099:
        return cardinal(n // 100) + " " + plural_number(n % 100)
    w = cardinal(n)
    return w[:-1] + "ies" if w.endswith("y") else w + "s"


def year_words(y: int) -> list[str]:
    """1988 -> nineteen eighty-eight, 1905 -> nineteen oh five, 1900 -> nineteen hundred, 2026 -> twenty twenty-six,
    2005 -> two thousand five."""
    if 2000 <= y <= 2009 or y < 1000 or y > 2099:
        return cardinal(y).split(" ")
    hi, lo = divmod(y, 100)
    if lo == 0:
        return [cardinal(hi), "hundred"]
    return [cardinal(hi)] + (["oh", ONES[lo]] if lo < 10 else [cardinal(lo)])


def pair_words(n: int) -> list[str]:
    """A house, box or room number said in pairs: 1600 -> sixteen hundred, 1187 -> eleven eighty-seven."""
    if n % 1000 == 0:
        return cardinal(n).split(" ")
    return year_words(n) if 1000 <= n <= 9999 else cardinal(n).split(" ")


def digit_words(s: str, zero: str = "zero") -> list[str]:
    return [zero if c == "0" else ONES[int(c)] for c in s if c.isdigit()]


MONTHS = ("January February March April May June July August September October November December").split()
MONTH_ABBR = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
              "nov": 11, "dec": 12}
DAY_ABBR = {"mon": "Monday", "tue": "Tuesday", "tues": "Tuesday", "wed": "Wednesday", "thu": "Thursday",
            "thur": "Thursday", "thurs": "Thursday", "fri": "Friday", "sat": "Saturday", "sun": "Sunday"}
# abbreviation + "." -> words; a title goes before a name, a street type after one
TITLE_ABBR = {"ms": "Miz", "prof": "Professor", "mt": "Mount", "ft": "Fort", "sgt": "Sergeant", "capt": "Captain", "lt": "Lieutenant", "gen": "General",
              "gov": "Governor", "sen": "Senator", "rep": "Representative", "rev": "Reverend", "col": "Colonel",
              "cpl": "Corporal", "adm": "Admiral", "pres": "President", "supt": "Superintendent", "hon": "Honorable"}
STREET_ABBR = {"st": "Street", "dr": "Drive", "ave": "Avenue", "av": "Avenue", "blvd": "Boulevard", "rd": "Road",
               "ln": "Lane", "ct": "Court", "pl": "Place", "pkwy": "Parkway", "hwy": "Highway", "sq": "Square",
               "ter": "Terrace", "cir": "Circle", "jr": "Junior", "sr": "Senior"}
WORD_ABBR = {"vs": "versus", "e.g": "for example", "approx": "approximately", "apt": "apartment",
             "dept": "department", "est": "established", "fig": "figure", "vol": "volume", "ch": "chapter",
             "pp": "pages", "ca": "circa", "cf": "compare", "corp": "corporation", "inc": "incorporated",
             "ltd": "limited", "govt": "government", "intl": "international", "misc": "miscellaneous",
             "dept.": "department", "yr": "year", "yrs": "years", "mo": "month", "mos": "months", "wk": "week",
             "wks": "weeks", "hr": "hour", "hrs": "hours", "min": "minute", "mins": "minutes", "sec": "second",
             "secs": "seconds", "tsp": "teaspoon", "tbsp": "tablespoon", "oz": "ounce", "lb": "pound", "lbs": "pounds",
             "pt": "pint", "qt": "quart", "gal": "gallon", "in": "inch", "ft": "foot", "yd": "yard", "mi": "mile"}
# a unit after a number: (singular, plural); case matters ("mA" is not "MA")
UNITS = {
    "km": ("kilometer", "kilometers"), "cm": ("centimeter", "centimeters"), "mm": ("millimeter", "millimeters"),
    "m": ("meter", "meters"), "kg": ("kilogram", "kilograms"), "g": ("gram", "grams"), "mg": ("milligram", "milligrams"),
    "lb": ("pound", "pounds"), "lbs": ("pound", "pounds"), "oz": ("ounce", "ounces"), "ft": ("foot", "feet"),
    "mi": ("mile", "miles"), "yd": ("yard", "yards"), "yds": ("yard", "yards"), "mph": ("mile per hour", "miles per hour"),
    "kph": ("kilometer per hour", "kilometers per hour"), "km/h": ("kilometer per hour", "kilometers per hour"),
    "ml": ("milliliter", "milliliters"), "mL": ("milliliter", "milliliters"), "L": ("liter", "liters"),
    "gal": ("gallon", "gallons"), "qt": ("quart", "quarts"), "tsp": ("teaspoon", "teaspoons"),
    "tbsp": ("tablespoon", "tablespoons"), "Tbsp": ("tablespoon", "tablespoons"), "kWh": ("kilowatt hour", "kilowatt hours"),
    "Wh": ("watt hour", "watt hours"), "W": ("watt", "watts"), "kW": ("kilowatt", "kilowatts"),
    "MW": ("megawatt", "megawatts"), "mW": ("milliwatt", "milliwatts"), "V": ("volt", "volts"), "mV": ("millivolt", "millivolts"),
    "kV": ("kilovolt", "kilovolts"), "mA": ("milliamp", "milliamps"), "mAh": ("milliamp hour", "milliamp hours"),
    "Hz": ("hertz", "hertz"), "kHz": ("kilohertz", "kilohertz"), "MHz": ("megahertz", "megahertz"),
    "GHz": ("gigahertz", "gigahertz"), "KB": ("kilobyte", "kilobytes"), "kB": ("kilobyte", "kilobytes"),
    "MB": ("megabyte", "megabytes"), "GB": ("gigabyte", "gigabytes"), "TB": ("terabyte", "terabytes"),
    "Mbps": ("megabit per second", "megabits per second"), "Gbps": ("gigabit per second", "gigabits per second"),
    "ms": ("millisecond", "milliseconds"), "sec": ("second", "seconds"), "secs": ("second", "seconds"),
    "min": ("minute", "minutes"), "mins": ("minute", "minutes"), "hr": ("hour", "hours"), "hrs": ("hour", "hours"),
}
UNITS.update({"µm": ("micrometer", "micrometers"), "μm": ("micrometer", "micrometers"), "nm": ("nanometer", "nanometers"),
              "µs": ("microsecond", "microseconds"), "μs": ("microsecond", "microseconds"),
              "ns": ("nanosecond", "nanoseconds"), "µg": ("microgram", "micrograms"), "mcg": ("microgram", "micrograms"),
              "µA": ("microamp", "microamps"), "uA": ("microamp", "microamps"), "dB": ("decibel", "decibels"),
              "rpm": ("R P M", "R P M"), "psi": ("P S I", "P S I")})
UNIT_GLUED = re.compile(r"^(\d[\d,]*(?:\.\d+)?)(km|cm|mm|nm|µm|μm|kg|mg|µg|mcg|lbs?|oz|ft|mi|mph|kph|ml|mL|tsp|tbsp|"
                        r"kWh|Wh|kW|MW|mW|W|mV|kV|V|mAh|mA|µA|Hz|kHz|MHz|GHz|KB|kB|MB|GB|TB|Mbps|Gbps|ms|µs|ns|"
                        r"hrs?|mins?|secs?|dB|rpm|psi)$")
CURRENCY = {"$": ("dollar", "dollars", "cent", "cents"), "€": ("euro", "euros", "cent", "cents"),
            "£": ("pound", "pounds", "penny", "pence"), "¥": ("yen", "yen", "", ""), "₹": ("rupee", "rupees", "", "")}
SCALES = {"k": "thousand", "K": "thousand", "m": "million", "M": "million", "mm": "million", "b": "billion",
          "B": "billion", "bn": "billion", "t": "trillion", "T": "trillion"}
SCALE_WORDS = {"thousand", "million", "billion", "trillion"}
# a money amount before one of these is said singular ("a $100 gift card" -> a 100 dollar gift card)
ATTRIBUTIVE = {"bill", "bills", "note", "notes", "gift", "fee", "fine", "item", "items", "deal", "coupon", "voucher",
               "check", "cheque", "ticket", "tickets", "bet", "card", "cards", "bonus", "credit", "tip", "donation",
               "minimum", "purchase", "order", "prize", "reward", "discount", "charge", "surcharge", "increase",
               "raise", "loan", "budget", "bottle", "meal", "value", "pledge", "deposit", "fare", "toll", "coin",
               "coins", "piece", "pieces", "box", "kit", "bag", "plan", "subscription", "membership"}
PER_UNIT = {"month": "a month", "mo": "a month", "year": "a year", "yr": "a year", "week": "a week", "wk": "a week",
            "day": "a day", "hour": "an hour", "hr": "an hour", "night": "a night", "person": "a person",
            "head": "a head", "kg": "a kilo", "lb": "a pound", "unit": "a unit", "user": "a user", "seat": "a seat",
            "share": "a share", "gallon": "a gallon", "mile": "a mile", "minute": "a minute"}
VERSION_CUE = {"version", "v", "release", "python", "node", "ios", "ipados", "macos", "android", "java", "ruby", "php",
               "perl", "rust", "go", "kotlin", "swift", "ubuntu", "debian", "fedora", "windows", "firmware",
               "kernel", "build", "update", "chrome", "firefox", "safari", "linux", "gcc", "clang", "llvm", "cuda",
               "numpy", "torch", "pytorch", "django", "rails", "react", "typescript", "xcode", "unity", "blender",
               "bluetooth", "http", "usb", "opengl", "vulkan", "tls", "ssl", "osx", "watchos", "tvos", "visionos",
               "gpt", "llama", "claude", "gemini", "qwen", "mistral", "pip", "npm", "openssl", "postgres", "mysql"}
# capitals said as a word, not spelled
ACRONYM_WORDS = {"FAQ", "GIF", "SIM", "PIN", "RAM", "LAN", "WAN", "ZIP", "CAD", "DOS", "ROM", "HUD", "TED", "SAT",
                 "ASAP", "NASA", "NATO", "SCUBA", "LASER", "RADAR", "AIDS", "OPEC", "FEMA", "UNICEF", "UNESCO", "MOMA",
                 "CERN", "IKEA", "JPEG", "PEG", "WASP", "SWAT", "SARS", "COVID", "GUI", "API", "ACK", "NAT", "VAT",
                 "CAP", "MAD", "BAM", "POW", "MIA", "HAL", "NOW", "BRB", "LOL", "OMG", "WOW", "YES", "OK", "TBA",
                 "PAC", "SAG", "CON", "PRO", "MAX", "MIN", "DEV", "OPS", "LIT", "MET", "SAC", "VAC", "MAG", "GEN"}
SHORTHAND = {"imo": "in my opinion", "imho": "in my humble opinion", "eod": "end of day", "btw": "by the way",
             "tbd": "to be determined", "tba": "to be announced", "pls": "please", "plz": "please", "thx": "thanks",
             "pw": "password", "re": "regarding", "dept": "department", "pts": "points", "approx": "approximately"}
SHORTHAND_CASED = {"IMO": "in my opinion", "IMHO": "in my humble opinion", "EOD": "end of day", "BTW": "by the way",
                   "TBD": "to be determined", "TBA": "to be announced", "OT": "overtime", "TDs": "touchdowns",
                   "INTs": "interceptions"}
ZONES = {"ET": "Eastern Time", "PT": "Pacific Time", "CT": "Central Time", "MT": "Mountain Time",
         "HST": "Hawaii time", "UTC": "U T C", "GMT": "G M T"}
LETTER_CUE = {"series", "class", "type", "plan", "grade", "vitamin", "group", "section", "exhibit", "appendix",
              "option", "model", "building", "terminal", "gate", "row", "level", "platform", "tier", "phase", "zone",
              "block", "wing", "unit", "part", "item", "list", "team", "side", "track", "lot", "concourse"}
NUMBER_WORDS = {"two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven", "twelve", "twenty",
                "dozen", "hundred"}
MINUTE_NOUNS = {"crack", "cracks", "hole", "holes", "scratch", "scratches", "fragment", "fragments", "detail",
                "details", "speck", "specks", "dose", "doses", "crystal", "crystals", "grain", "grains", "particle",
                "particles", "trace", "traces", "amount", "amounts", "fraction", "difference", "differences",
                "change", "changes", "flaw", "flaws", "quantity", "quantities", "tear", "leak", "bubble", "bubbles"}
DIRECTIONS = {"n": "North", "s": "South", "e": "East", "w": "West", "ne": "Northeast", "nw": "Northwest",
              "se": "Southeast", "sw": "Southwest"}
STREET_WORDS = {"st", "street", "ave", "avenue", "blvd", "boulevard", "rd", "road", "dr", "drive", "ln", "lane",
                "way", "ct", "court", "pl", "place", "pkwy", "parkway", "hwy", "highway", "ter", "terrace", "cir",
                "circle", "sq", "square", "trl", "trail", "loop", "row", "box"}
STATES = {"AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
          "CT": "Connecticut", "DE": "Delaware", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
          "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas", "KY": "Kentucky", "LA": "Louisiana",
          "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
          "MS": "Mississippi", "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
          "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York", "NC": "North Carolina",
          "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
          "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas",
          "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
          "WI": "Wisconsin", "WY": "Wyoming", "DC": "D C"}
TLDS = {"com", "org", "net", "edu", "gov", "io", "ai", "co", "uk", "us", "dev", "app", "info", "me", "tv", "ly", "gg",
        "xyz", "biz", "ca", "de", "fr", "jp", "au", "in", "nz", "ie", "es", "it", "nl", "ch", "se", "no", "fi", "be",
        "at", "mil", "int", "eu", "fm", "am", "so", "sh", "to", "cc", "tech", "site", "online", "store", "blog", "news",
        "page", "cloud", "health", "art", "design", "studio", "games", "live", "chat", "email", "global", "today", "world"}
TLD_SAY = {"com": "com", "org": "org", "net": "net", "gov": "gov", "co": "co", "info": "info", "app": "app", "dev": "dev",
           "me": "me", "blog": "blog", "news": "news", "tech": "tech", "site": "site", "online": "online",
           "store": "store", "page": "page", "cloud": "cloud", "health": "health", "art": "art", "design": "design",
           "studio": "studio", "games": "games", "live": "live", "chat": "chat", "email": "email", "global": "global",
           "today": "today", "world": "world", "biz": "biz", "mil": "mil"}
SEP_WORDS = {".": "dot", "_": "underscore", "-": "dash", "+": "plus", "/": "slash", "~": "tilde", "=": "equals",
             "?": "question mark", "&": "and", "#": "hash", ":": "colon", "%": "percent"}
REGNAL = {"henry", "elizabeth", "louis", "george", "edward", "charles", "james", "william", "john", "richard", "paul",
          "pius", "benedict", "leo", "gregory", "innocent", "clement", "alexander", "napoleon", "philip", "frederick",
          "ferdinand", "peter", "catherine", "mary", "anne", "juan", "carlos", "felipe", "ramses", "constantine",
          "otto", "ludwig", "gustav", "christian", "olaf", "harald", "haakon", "nicholas", "ivan", "francis", "henri",
          "albert", "pedro", "sebastian", "martin", "urban", "boniface", "sixtus", "julius", "adrian", "hadrian",
          "rama", "victor", "umberto", "alfonso", "sancho", "baldwin", "david", "malcolm", "robert", "stephen",
          "kamehameha", "wilhelm", "leopold", "rudolf", "joseph", "willem", "carl", "frederik", "margrethe", "dmitry"}
ROMAN_CUE = {"war", "chapter", "part", "volume", "vol", "act", "book", "phase", "type", "class", "level", "section",
             "article", "title", "grade", "stage", "episode", "season", "bowl", "apollo", "gemini", "mark", "mk",
             "series", "round", "tier", "category", "schedule", "appendix", "unit", "rule", "step", "psalm", "canto",
             "scene", "game", "olympiad", "vatican", "council", "amendment", "division", "corps", "fleet", "army",
             "clause", "paragraph", "tome", "symphony", "lesson", "module", "track", "mission", "operation"}
ROMAN_AMBIGUOUS = {"IV", "XL", "LV", "LX", "XX", "XXX", "VL", "IL", "LI", "MIX", "DIV", "CIV", "VI", "XI", "IX", "CI",
                   "CL", "CV", "DC", "CD", "MD", "MC", "MCC", "LXX", "XXL", "XXXL"}
ROMAN = re.compile(r"^(?=[IVXLCDM])M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$")
# names and words both engines say wrong (base phonemes; the context model still places them in the clause)
SAY_AS = {"haumea": "hWmˈAə", "leokani": "lˌAOkˈɑni", "mahalo": "məhˈɑlO", "kamehameha": "kəmˌAəmˈAhə",
          "waikiki": "wˌIkɪkˈi", "kauai": "kəwˈI", "kolea": "kOlˈAə", "mauna": "mˈWnə", "kea": "kˈAə",
          "molokai": "mˌOlOkˈI", "lanai": "lənˈI", "hilo": "hˈilO", "pele": "pˈɛlA", "kahului": "kˌɑhulˈui",
          "wahine": "wɑhˈinA", "nguyen": "wˈɪn", "joaquin": "wɑkˈin", "nietzsche": "nˈiʧə", "ballets": "bælˈAz",
          "milliwatt": "mˈɪlɪwˌɑt", "xochitl": "sˈOʧil", "oaxaca": "wəhˈɑkə", "lanikai": "lˌɑnikˈI",
          "niamh": "nˈiv", "saoirse": "sˈɪɹʃə", "przybylski": "ʃəbˈɪlski", "keanu": "kAˈɑnu", "versailles": "vəɹsˈI",
          "haagen-dazs": "hˈɑɡən dˈɑz", "nescafe": "nˈɛskəfˌA", "moet": "mOˈɛt", "huawei": "wˈɑwA",
          "aoife": "ˈifə", "quinoa": "kˈinwɑ", "sriracha": "sɹˈiɹɑʧə", "gnocchi": "nˈjɑki",
          "xavier": "zˈAviəɹ", "haleakala": "hˌɑlAˌɑkəlˈɑ", "kalapana": "kˌɑləpˈɑnə", "ngozi": "əŋɡˈOzi",
          "okonkwo": "OkˈɔŋkwO", "waimea": "wˌImˈAə", "briain": "bɹˈiən",
          "hermes": "ɛɹmˈɛz", "nike": "nˈIki", "adidas": "ədˈidəs", "hyundai": "hˈʌndA", "ioniq": "Iˈɑnɪk",
          "xiaomi": "ʃˈWmi", "lebron": "ləbɹˈɑn", "porsche": "pˈɔɹʃə"}
SAY_AS_CASED = {"LaTeX": "lˈAtɛk", "iOS": "ˌIˌOˈɛs", "macOS": "mˌækˌOˈɛs", "watchOS": "wˌɑʧˌOˈɛs",
                "tvOS": "tˌivˌiˌOˈɛs", "iPadOS": "ˈIpˌædˌOˈɛs", "Wi-Fi": "wˈIfˌI", "WiFi": "wˈIfˌI",
                "SQL": "sˈikwᵊl", "RAM": "ɹˈæm", "ETA": "ˌiˌtiˈA", "YoY": "jˈɪɹ ˌOvəɹ jˈɪɹ", "IKEA": "Ikˈiə",
                "MacBook": "mˈækbʊk", "FEMA": "fˈimə", "ZIP": "zˈɪp",
                "eSIM": "ˈi sˈɪm", "eSIMs": "ˈi sˈɪmz"}
# heteronyms the context model takes the wrong way after these words
VERB_BEFORE = {"to", "will", "would", "can", "could", "should", "must", "may", "might", "please", "we", "i", "eye",
               "they", "you", "don't", "didn't", "won't", "let's", "i'll", "we'll", "they'll", "you'll", "always",
               "never", "often", "also", "still", "just", "do", "did", "people", "who"}
ADJ_FORMS = {"minute": "mInˈut", "content": "kəntˈɛnt"}
VERB_FORMS = {"present": "pɹɪzˈɛnt", "convict": "kənvˈɪkt", "subject": "səbʤˈɛkt", "insult": "ɪnsˈʌlt",
              "decrease": "dᵻkɹˈis", "live": "lˈɪv"}
SUBJECTS = {"he", "she", "it", "they", "we", "i", "eye", "you", "who"}
OBJECTS = {"the", "a", "an", "your", "my", "our", "his", "her", "their", "its", "it", "this", "that", "these", "those",
           "them", "him", "me", "us", "up", "down", "all", "everything", "off", "out"}
# ---- letters and codes (v1.2)
# capitals respelled as words ("IEEE" -> I triple E); the respelling goes through the normaliser again
CASED_SAY = {"IEEE": "I triple E", "WWI": "World War one", "WWII": "World War two", "WW1": "World War one",
             "WW2": "World War two", "PhD": "P H D", "PhDs": "P H Ds",
             "ZIP+4": "zip plus four", "A-OK": "A O K", "AAA": "triple A", "NAACP": "N double A C P", "NCAA": "N C double A"}
# a digit run after one of these is a code said digit by digit ("tracking number 9400111899", "code 482913")
CODE_CUE = {"number", "code", "pin", "passcode", "otp", "account", "tracking", "order", "confirmation",
            "reference", "ref", "serial", "invoice", "ticket", "sn", "policy", "member", "membership", "case",
            "claim", "booking", "voucher", "pnr", "id", "acct", "routing", "transaction", "receipt", "badge",
            "verification", "security", "access", "promo", "coupon", "shipment", "parcel", "package", "#"}
# an all-caps word the letter-to-sound model doesn't know is said as a word only if English could spell it:
# a legal onset, vowels, consonant clusters that split into a legal coda and onset, a legal coda
ONSETS = set("b c d f g h j k l m n p q r s t v w x y z bl br ch cl cr dr dw fl fr gl gn gr kl kn kr ph pl pr ps qu "
             "sc sch scr sh shr sk sl sm sn sp spl spr squ st str sw th thr tr tw wh wr chr phr sph tw".split()) | {""}
CODAS = set("b c d f g k l m n p r s t v x z ck ct ft ld lf lk lm lp lt mb mp nd ng nk ns nt nch rb rc rd rf rg rk "
            "rl rm rn rp rs rt sh sk sp st th tch ts ds ks ps ch ght gh ll ss ff zz rth rst nds nts mps rks lls ch "
            "rch lch nce rse lse wn wl wk ws wd y w h".split()) | {""}
# words that start a sentence after a single letter and a full stop ("Plan A. Then we ..."), not a name after an initial
SENTENCE_START = set("the then we i it he she they this that a an and but so now there you my our in on at if when after "
                     "before what why how next first finally also please".split())
# letters said in the plural: the sibilant letters take "-es"
LETTER_PLURAL_ES = set("sxhz")
LETTER_PLURAL_S = set("f")


def pronounceable(w: str) -> bool:
    """Could an English reader say this all-letter run as a word ("BLORB" yes, "AGC" or "QRT" no)?"""
    w = w.lower()
    if not w.isascii() or not w.isalpha():
        return False
    if len(w) <= 3:                                          # short ones only as one closed syllable ("HUD")
        return bool(re.match(r"^[bcdfghjklmnpqrstvwxz]?[aeiou][bcdfgklmnprstvxz]?$", w))
    # vowel groups; a "y" before a vowel or at the start is a consonant
    groups = re.findall(r"[aeiou]+|(?<=[^aeiou])y(?![aeiou])|[^aeiou]", w)
    vowel = lambda g: g[0] in "aeiou" or g == "y"  # noqa: E731
    merged: list[str] = []
    for g in groups:
        if merged and not vowel(g) and not vowel(merged[-1]):
            merged[-1] += g
        else:
            merged.append(g)
    vows = [g for g in merged if vowel(g)]
    if not vows or any(len(v) > 2 for v in vows):
        return False
    for k, g in enumerate(merged):
        if vowel(g):
            continue
        if k == 0:
            if g not in ONSETS:
                return False
        elif k == len(merged) - 1:
            if g not in CODAS:
                return False
        elif not any(g[:j] in CODAS and g[j:] in ONSETS for j in range(len(g) + 1)) or len(g) > 4:
            return False
    return True


# ---- homographs (v1.2). HOMOGRAPHS[word] = [(phonemes, tests), ...]: the first rule whose tests all hold says the
# word with those phonemes ("" = leave it to the context model). A test is FIELD OP VALUES: FIELD p1 p2 p3 (the words
# before, "^" past the clause start), n1 n2 n3 (after, "$" past its end), P / N (any of p1-p3 / n1-n3); OP "=" (one
# of), "!=" (none of), "~" (ends with one of), "!~" (ends with none of); VALUES "|"-separated words, "@NAME" a HG_CLASSES set. "cap": the
# word is capitalised and not clause-initial. Context words are lowercase without surrounding punctuation.
HG_STOP = set(".,!?;:…—–")
HG_CLASSES = {
    "DET": "the a an this that these those my your his her its our their no any some every each another which what "
           "whose one two three several many few more most such either neither",
    "MODAL": "will would can could should must may might shall can't won't wouldn't couldn't shouldn't cannot "
             "i'll you'll we'll they'll he'll she'll it'll i'd you'd we'd they'd he'd she'd",
    "DO": "do does did don't doesn't didn't",
    "SUBJ": "i you we they he she who eye",
    "BE": "am is are was were be been being isn't aren't wasn't weren't it's that's there's he's she's what's",
    "HAVE": "have has had having haven't hasn't hadn't i've you've we've they've",
    "PREP": "of in on at for with from by into onto about under over through after before during without against "
            "between among near behind across around toward towards upon within like",
    "ADV": "not never also always often still just really usually already even soon then now quickly carefully "
           "rarely sometimes probably finally actually",
    "OBJ": "the a an your my our his her their its it this that these those them him me us you everything "
           "something anything everyone someone some all both",
    # a determiner before a noun; the ones that also start a noun phrase after a verb
    "DETN": "the a an my your his her its our their this these those no any some every each another which whose "
            "several many few most such what",
    "DETX": "the a an your my our his their its this these those",
    "SUBJX": "i you we they he she who anyone everyone someone nobody people",
    # what follows an imperative verb at the start of a clause
    "IMPN": "the a an your my our his her their its it this that these those them him me us everything "
            "something all both between along into out up with off from across through over around down",
    # words ending in -s that aren't a plural subject
    "NOTPL": "this his is was has does as us plus thus less always perhaps sometimes its yes lots whereas "
             "afterwards besides towards upwards news means series species politics physics",
}
# HOMOGRAPHS-BEGIN (generated by g2p_hgtable.py; edit the templates there, not this block)
HOMOGRAPHS: dict[str, list[tuple[str, list[str]]]] = {
    'address': [
        ('', ["p1=^", "N=address|addresss"]),
        ('', ["p2=address|addresss", "p3=^"]),
        ('ˈædɹɛs', ["p1=@DETN", "n1!=@DETX"]),
        ('ədɹˈɛs', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ədɹˈɛs', ["p1=@SUBJX"]),
        ('ədɹˈɛs', ["p1=^|please", "n1=@IMPN"]),
        ('ədɹˈɛs', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ədɹˈɛs', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ədɹˈɛs', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ədɹˈɛs', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'aged': [
        ('ˈAʤᵻd', ["p1=the|an|@DETN", "n1=and|or|$|who|are|were|people|parents|mother|father|man|woman|couple|relatives|population|care|home|homes|patients|grandmother|grandfather|relative"]),
    ],
    'alternate': [
        ('ɔltˈɜɹnət', ["p1=@DETN", "n1!=@DETX"]),
        ('ɔltˈɜɹnət', ["p1=@BE|very|more|most|less|quite|so|too|perfectly|entirely|completely|fully|highly|rather|not|seem|seems|seemed|look|looks|looked|feel|feels|felt|become|became"]),
        ('ˈɔltəɹnˌAt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ˈɔltəɹnˌAt', ["p1=@SUBJX"]),
        ('ˈɔltəɹnˌAt', ["p1=^|please", "n1=@IMPN"]),
        ('ˈɔltəɹnˌAt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ˈɔltəɹnˌAt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ˈɔltəɹnˌAt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
    ],
    'appropriate': [
        ('əpɹˈOpɹɪjət', ["p1=@DETN", "n1!=@DETX"]),
        ('əpɹˈOpɹɪjət', ["p1=@BE|very|more|most|less|quite|so|too|perfectly|entirely|completely|fully|highly|rather|not|seem|seems|seemed|look|looks|looked|feel|feels|felt|become|became"]),
        ('əpɹˈOpɹɪˌAt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('əpɹˈOpɹɪˌAt', ["p1=@SUBJX"]),
        ('əpɹˈOpɹɪˌAt', ["p1=^|please", "n1=@IMPN"]),
        ('əpɹˈOpɹɪˌAt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('əpɹˈOpɹɪˌAt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('əpɹˈOpɹɪˌAt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
    ],
    'associate': [
        ('', ["p1=^", "N=associate|associates"]),
        ('', ["p2=associate|associates", "p3=^"]),
        ('əsˈOsiət', ["p1=@DETN", "n1!=@DETX"]),
        ('əsˈOsɪˌAt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('əsˈOsɪˌAt', ["p1=@SUBJX"]),
        ('əsˈOsɪˌAt', ["p1=^|please", "n1=@IMPN"]),
        ('əsˈOsɪˌAt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('əsˈOsɪˌAt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('əsˈOsɪˌAt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('əsˈOsɪˌAt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'attribute': [
        ('', ["p1=^", "N=attribute|attributes"]),
        ('', ["p2=attribute|attributes", "p3=^"]),
        ('ˈætɹɪbjˌut', ["p1=@DETN", "n1!=@DETX"]),
        ('ətɹˈɪbjut', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ətɹˈɪbjut', ["p1=@SUBJX"]),
        ('ətɹˈɪbjut', ["p1=^|please", "n1=@IMPN"]),
        ('ətɹˈɪbjut', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ətɹˈɪbjut', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ətɹˈɪbjut', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ətɹˈɪbjut', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'axes': [
        ('ˈæksiz', ["P=graph|graphs|chart|plot|logarithmic|coordinate|coordinates|both|x|y|z|horizontal|vertical|principal|rotation|label|labels|labeled|scale|scales|grid|symmetry|cartesian|plotted|axis|figure|three|two"]),
        ('ˈæksiz', ["N=graph|graphs|chart|plot|labeled|symmetry|rotation|grid|x|y|z"]),
    ],
    'bases': [
        ('bˈAsiz', ["n1=for"]),
        ('bˈAsiz', ["P=no|legal|theoretical|factual|scientific|moral|ethical|constitutional|statutory|logical|empirical|valid|solid|sound|possible|several|multiple|various"]),
    ],
    'blessed': [
        ('blˈɛsᵻd', ["p1=every|a|this|that|the|most|thrice|holy|ever|our|your|his|her|my|truly|so|such", "n1!=with|by|to|$|and"]),
    ],
    'bow': [
        ('bˈW', ["n1=of", "N=ship|boat|vessel|yacht|canoe|ferry|tanker|liner|kayak|freighter|ships|boats"]),
        ('bˈO', ["P=rosined|rosin|violin|cello|viola|fiddle|arrow|arrows|archer|archery|ribbon|tied|tie|pink|red|silk|velvet|hair|bright|cross"]),
        ('bˈW', ["p1=@SUBJX|@MODAL|to|and|then|please|^", "n1=to|down|before|deeply|low|his|her|their|our|in|politely|slightly|respectfully|out"]),
    ],
    'bows': [
        ('bˈWz', ["p1!=@DETN", "n1=his|her|their|to|down|before|deeply|low|politely|slightly|respectfully|out|in"]),
    ],
    'buffet': [
        ('bˈʌfɪt', ["p1!=@DETN", "n1=@OBJ"]),
        ('bəfˈA', ["P=@DETN|chinese|breakfast|lunch|dinner|salad|seafood|dessert|hotel|brunch|cold|hot|all-you-can-eat|indian|italian"]),
    ],
    'compound': [
        ('', ["p1=^", "N=compound|compounds"]),
        ('', ["p2=compound|compounds", "p3=^"]),
        ('kˈɑmpWnd', ["p1=@DETN", "n1!=@DETX"]),
        ('kɑmpˈWnd', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('kɑmpˈWnd', ["p1=@SUBJX"]),
        ('kɑmpˈWnd', ["p1=^|please", "n1=@IMPN"]),
        ('kɑmpˈWnd', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('kɑmpˈWnd', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('kɑmpˈWnd', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('kɑmpˈWnd', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'conduct': [
        ('', ["p1=^", "N=conduct|conducts"]),
        ('', ["p2=conduct|conducts", "p3=^"]),
        ('kˈɑndʌkt', ["p1=@DETN", "n1!=@DETX"]),
        ('kəndˈʌkt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('kəndˈʌkt', ["p1=@SUBJX"]),
        ('kəndˈʌkt', ["p1=^|please", "n1=@IMPN"]),
        ('kəndˈʌkt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('kəndˈʌkt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('kəndˈʌkt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('kəndˈʌkt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'conflict': [
        ('', ["p1=^", "N=conflict|conflicts"]),
        ('', ["p2=conflict|conflicts", "p3=^"]),
        ('kˈɑnflɪkt', ["p1=@DETN", "n1!=@DETX"]),
        ('kənflˈɪkt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('kənflˈɪkt', ["p1=@SUBJX"]),
        ('kənflˈɪkt', ["p1=^|please", "n1=@IMPN"]),
        ('kənflˈɪkt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('kənflˈɪkt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('kənflˈɪkt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('kənflˈɪkt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'console': [
        ('', ["p1=^", "N=console|consoles"]),
        ('', ["p2=console|consoles", "p3=^"]),
        ('kˈɑnsOl', ["p1=@DETN", "n1!=@DETX"]),
        ('kənsˈOl', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('kənsˈOl', ["p1=@SUBJX"]),
        ('kənsˈOl', ["p1=^|please", "n1=@IMPN"]),
        ('kənsˈOl', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('kənsˈOl', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('kənsˈOl', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('kənsˈOl', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'contract': [
        ('', ["p1=^", "N=contract|contracts"]),
        ('', ["p2=contract|contracts", "p3=^"]),
        ('kˈɑntɹækt', ["p1=@DETN", "n1!=@DETX"]),
        ('kəntɹˈækt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('kəntɹˈækt', ["p1=@SUBJX"]),
        ('kəntɹˈækt', ["p1=^|please", "n1=@IMPN"]),
        ('kəntɹˈækt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('kəntɹˈækt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('kəntɹˈækt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('kəntɹˈækt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'convict': [
        ('', ["p1=^", "N=convict|convicts"]),
        ('', ["p2=convict|convicts", "p3=^"]),
        ('kˈɑnvɪkt', ["p1=@DETN", "n1!=@DETX"]),
        ('kənvˈɪkt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('kənvˈɪkt', ["p1=@SUBJX"]),
        ('kənvˈɪkt', ["p1=^|please", "n1=@IMPN"]),
        ('kənvˈɪkt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('kənvˈɪkt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('kənvˈɪkt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('kənvˈɪkt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'deliberate': [
        ('dᵻlˈɪbəɹɹət', ["p1=@DETN", "n1!=@DETX"]),
        ('dᵻlˈɪbəɹɹət', ["p1=@BE|very|more|most|less|quite|so|too|perfectly|entirely|completely|fully|highly|rather|not|seem|seems|seemed|look|looks|looked|feel|feels|felt|become|became"]),
        ('dᵻlˈɪbəɹɹˌAt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('dᵻlˈɪbəɹɹˌAt', ["p1=@SUBJX"]),
        ('dᵻlˈɪbəɹɹˌAt', ["p1=^|please", "n1=@IMPN"]),
        ('dᵻlˈɪbəɹɹˌAt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('dᵻlˈɪbəɹɹˌAt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('dᵻlˈɪbəɹɹˌAt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
    ],
    'desert': [
        ('', ["p1=^", "N=desert|deserts"]),
        ('', ["p2=desert|deserts", "p3=^"]),
        ('dˈɛzəɹt', ["p1=@DETN", "n1!=@DETX"]),
        ('dᵻzˈɜɹt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('dᵻzˈɜɹt', ["p1=@SUBJX"]),
        ('dᵻzˈɜɹt', ["p1=^|please", "n1=@IMPN"]),
        ('dᵻzˈɜɹt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('dᵻzˈɜɹt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('dᵻzˈɜɹt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('dᵻzˈɜɹt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'digest': [
        ('dˈIʤɛst', ["cap"]),
        ('dˈIʤɛst', ["p1=weekly|daily|monthly|news|email|reader's"]),
        ('', ["p1=^", "N=digest|digests"]),
        ('', ["p2=digest|digests", "p3=^"]),
        ('dˈIʤɛst', ["p1=@DETN", "n1!=@DETX"]),
        ('dIʤˈɛst', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('dIʤˈɛst', ["p1=@SUBJX"]),
        ('dIʤˈɛst', ["p1=^|please", "n1=@IMPN"]),
        ('dIʤˈɛst', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('dIʤˈɛst', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('dIʤˈɛst', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('dIʤˈɛst', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'does': [
        ('dˈOz', ["p1=take|hunt|hunting|shoot|shot|killed|only|bucks|young|female|wild|pregnant|two|three|several|many|the|some", "n1=in|and|or|$|were|are|grazed|graze|grazing|at|from|during|with|on|that|which"]),
    ],
    'dove': [
        ('dˈʌv', ["p1=@DETN|white|mourning|peace|turtle|rock"]),
        ('dˈOv', ["n1=after|into|in|under|off|for|down|through|onto|deep|headfirst|back|to|from|nearly|sharply|below|toward|towards|behind|out|overboard|percent"]),
    ],
    'entrance': [
        ('', ["p1=^", "N=entrance|entrances"]),
        ('', ["p2=entrance|entrances", "p3=^"]),
        ('ˈɛntɹəns', ["p1=@DETN", "n1!=@DETX"]),
        ('ɛntɹˈæns', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɛntɹˈæns', ["p1=@SUBJX"]),
        ('ɛntɹˈæns', ["p1=^|please", "n1=@IMPN"]),
        ('ɛntɹˈæns', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɛntɹˈæns', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɛntɹˈæns', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɛntɹˈæns', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'estimate': [
        ('', ["p1=^", "N=estimate|estimates"]),
        ('', ["p2=estimate|estimates", "p3=^"]),
        ('ˈɛstᵻmət', ["p1=@DETN", "n1!=@DETX"]),
        ('ˈɛstᵻmˌAt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ˈɛstᵻmˌAt', ["p1=@SUBJX"]),
        ('ˈɛstᵻmˌAt', ["p1=^|please", "n1=@IMPN"]),
        ('ˈɛstᵻmˌAt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ˈɛstᵻmˌAt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ˈɛstᵻmˌAt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ˈɛstᵻmˌAt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'excuse': [
        ('', ["n1=me|us"]),
        ('', ["p1=^", "N=excuse|excuses"]),
        ('', ["p2=excuse|excuses", "p3=^"]),
        ('ɛkskjˈus', ["p1=@DETN", "n1!=@DETX"]),
        ('ɛkskjˈuz', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɛkskjˈuz', ["p1=@SUBJX"]),
        ('ɛkskjˈuz', ["p1=^|please", "n1=@IMPN"]),
        ('ɛkskjˈuz', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɛkskjˈuz', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɛkskjˈuz', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɛkskjˈuz', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'graduate': [
        ('', ["p1=^", "N=graduate|graduates"]),
        ('', ["p2=graduate|graduates", "p3=^"]),
        ('ɡɹˈæʤuət', ["p1=@DETN", "n1!=@DETX"]),
        ('ɡɹˈæʤuˌAt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɡɹˈæʤuˌAt', ["p1=@SUBJX"]),
        ('ɡɹˈæʤuˌAt', ["p1=^|please", "n1=@IMPN"]),
        ('ɡɹˈæʤuˌAt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɡɹˈæʤuˌAt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɡɹˈæʤuˌAt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɡɹˈæʤuˌAt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'house': [
        ('', ["p1=^", "N=house|houses"]),
        ('', ["p2=house|houses", "p3=^"]),
        ('hˈWs', ["p1=@DETN", "n1!=@DETX"]),
        ('hˈWz', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('hˈWz', ["p1=@SUBJX"]),
        ('hˈWz', ["p1=^|please", "n1=@IMPN"]),
        ('hˈWz', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('hˈWz', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('hˈWz', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('hˈWz', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'incense': [
        ('', ["p1=^", "N=incense|incenses"]),
        ('', ["p2=incense|incenses", "p3=^"]),
        ('ˈɪnsɛns', ["p1=@DETN", "n1!=@DETX"]),
        ('ɪnsˈɛns', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɪnsˈɛns', ["p1=@SUBJX"]),
        ('ɪnsˈɛns', ["p1=^|please", "n1=@IMPN"]),
        ('ɪnsˈɛns', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɪnsˈɛns', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɪnsˈɛns', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɪnsˈɛns', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'increase': [
        ('', ["p1=^", "N=increase|increases"]),
        ('', ["p2=increase|increases", "p3=^"]),
        ('ˈɪŋkɹis', ["p1=@DETN", "n1!=@DETX"]),
        ('ɪŋkɹˈis', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɪŋkɹˈis', ["p1=@SUBJX"]),
        ('ɪŋkɹˈis', ["p1=^|please", "n1=@IMPN"]),
        ('ɪŋkɹˈis', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɪŋkɹˈis', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɪŋkɹˈis', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɪŋkɹˈis', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'insert': [
        ('', ["p1=^", "N=insert|inserts"]),
        ('', ["p2=insert|inserts", "p3=^"]),
        ('ˈɪnsɜɹt', ["p1=@DETN", "n1!=@DETX"]),
        ('ɪnsˈɜɹt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɪnsˈɜɹt', ["p1=@SUBJX"]),
        ('ɪnsˈɜɹt', ["p1=^|please", "n1=@IMPN"]),
        ('ɪnsˈɜɹt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɪnsˈɜɹt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɪnsˈɜɹt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɪnsˈɜɹt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'invalid': [
        ('ˈɪnvəlɪd', ["p1=an|the|as", "n1=$|who|and|for|in|at|with"]),
    ],
    'lead': [
        ('lˈɛd', ["p1=pencil|graphite|mechanical|soft|hard|sharpened|sharp|toxic|molten|white|red"]),
        ('lˈɛd', ["n1=pipes|pipe|paint|poisoning|levels|contamination|exposure|bullet|bullets|shot|weight|weights|crystal|solder|acetate|oxide|apron|shielding|ore|mine|mines|pencil|pencils|piping|sinker|sinkers|balloon"]),
    ],
    'learned': [
        ('lˈɜɹnᵻd', ["p1=@DETN", "n1!=@DETX|to|from|that|how|about"]),
    ],
    'live': [
        ('lˈIv', ["n1=music|broadcast|broadcasts|show|shows|concert|concerts|wire|wires|audience|stream|streams|streaming|performance|performances|television|tv|coverage|event|events|bait|ammunition|rounds|feed|version|album|recording|recordings|action|animals|oak|chat|demo|video|videos|update|updates|band|bands|theater|theatre|sports|footage|cattle|webinar|session|sessions|blog|vote|grenade|round|wire's|q&a"]),
        ('lˈIv', ["p1=still|go|goes|went|going|gone|be|is|was|are|were|being|it's|now", "n1=$|on|from|at|tonight|now|in|with|and|right|today|this|across|for"]),
    ],
    'moderate': [
        ('mˈɑdəɹɹət', ["p1=@DETN", "n1!=@DETX"]),
        ('mˈɑdəɹɹət', ["p1=@BE|very|more|most|less|quite|so|too|perfectly|entirely|completely|fully|highly|rather|not|seem|seems|seemed|look|looks|looked|feel|feels|felt|become|became"]),
        ('mˈɑdəɹɹˌAt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('mˈɑdəɹɹˌAt', ["p1=@SUBJX"]),
        ('mˈɑdəɹɹˌAt', ["p1=^|please", "n1=@IMPN"]),
        ('mˈɑdəɹɹˌAt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('mˈɑdəɹɹˌAt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('mˈɑdəɹɹˌAt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
    ],
    'number': [
        ('nˈʌməɹ', ["n1=$|than|and", "P=feel|felt|feels|feeling|grew|growing|getting|became|become|went|gone|seemed|seems|looked"]),
    ],
    'object': [
        ('', ["p1=^", "N=object|objects"]),
        ('', ["p2=object|objects", "p3=^"]),
        ('ˈɑbʤɛkt', ["p1=@DETN", "n1!=@DETX"]),
        ('ɑbʤˈɛkt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɑbʤˈɛkt', ["p1=@SUBJX"]),
        ('ɑbʤˈɛkt', ["p1=^|please", "n1=@IMPN"]),
        ('ɑbʤˈɛkt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɑbʤˈɛkt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɑbʤˈɛkt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɑbʤˈɛkt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'perfect': [
        ('pˈɜɹfɛkt', ["p1=@DETN", "n1!=@DETX"]),
        ('pˈɜɹfɛkt', ["p1=@BE|very|more|most|less|quite|so|too|perfectly|entirely|completely|fully|highly|rather|not|seem|seems|seemed|look|looks|looked|feel|feels|felt|become|became"]),
        ('pəɹfˈɛkt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('pəɹfˈɛkt', ["p1=@SUBJX"]),
        ('pəɹfˈɛkt', ["p1=^|please", "n1=@IMPN"]),
        ('pəɹfˈɛkt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('pəɹfˈɛkt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('pəɹfˈɛkt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
    ],
    'permit': [
        ('', ["p1=^", "N=permit|permits"]),
        ('', ["p2=permit|permits", "p3=^"]),
        ('pˈɜɹmɪt', ["p1=@DETN", "n1!=@DETX"]),
        ('pəɹmˈɪt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('pəɹmˈɪt', ["p1=@SUBJX"]),
        ('pəɹmˈɪt', ["p1=^|please", "n1=@IMPN"]),
        ('pəɹmˈɪt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('pəɹmˈɪt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('pəɹmˈɪt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('pəɹmˈɪt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'present': [
        ('pɹˈɛzənt', ["p1=@DETN", "n1!=@DETX"]),
        ('pɹˈɛzənt', ["p1=@BE|very|more|most|less|quite|so|too|perfectly|entirely|completely|fully|highly|rather|not|seem|seems|seemed|look|looks|looked|feel|feels|felt|become|became"]),
        ('pɹɪzˈɛnt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('pɹɪzˈɛnt', ["p1=@SUBJX"]),
        ('pɹɪzˈɛnt', ["p1=^|please", "n1=@IMPN"]),
        ('pɹɪzˈɛnt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('pɹɪzˈɛnt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('pɹɪzˈɛnt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
    ],
    'primer': [
        ('pɹˈIməɹ', ["P=makeup|paint|painting|paints|foundation|skin|face|wall|walls|wood|metal|coat|coats|apply|applied|applying|spray|priming|eyeshadow|lipstick|sealant|drywall|surface|surfaces|rust|dna|pcr|sequencing|eye|lip|grip"]),
        ('pɹˈIməɹ', ["N=makeup|paint|painting|foundation|skin|face|wall|walls|wood|metal|coat|coats|dries|dry|spray|sealant|drywall|surface|surfaces|rust|dna|pcr|sequencing|eyeshadow|lipstick|helps|first"]),
    ],
    'produce': [
        ('pɹˈOdus', ["p1=all|fresh|local|organic|farm|seasonal|frozen|canned|wash|washed|our|your"]),
        ('', ["p1=^", "N=produce|produces"]),
        ('', ["p2=produce|produces", "p3=^"]),
        ('pɹˈOdus', ["p1=@DETN", "n1!=@DETX"]),
        ('pɹədˈus', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('pɹədˈus', ["p1=@SUBJX"]),
        ('pɹədˈus', ["p1=^|please", "n1=@IMPN"]),
        ('pɹədˈus', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('pɹədˈus', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('pɹədˈus', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('pɹədˈus', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'progress': [
        ('', ["p1=^", "N=progress|progresss"]),
        ('', ["p2=progress|progresss", "p3=^"]),
        ('pɹˈɑɡɹɛs', ["p1=@DETN", "n1!=@DETX"]),
        ('pɹəɡɹˈɛs', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('pɹəɡɹˈɛs', ["p1=@SUBJX"]),
        ('pɹəɡɹˈɛs', ["p1=^|please", "n1=@IMPN"]),
        ('pɹəɡɹˈɛs', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('pɹəɡɹˈɛs', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('pɹəɡɹˈɛs', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('pɹəɡɹˈɛs', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'project': [
        ('', ["p1=^", "N=project|projects"]),
        ('', ["p2=project|projects", "p3=^"]),
        ('pɹˈɑʤɛkt', ["p1=@DETN", "n1!=@DETX"]),
        ('pɹəʤˈɛkt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('pɹəʤˈɛkt', ["p1=@SUBJX"]),
        ('pɹəʤˈɛkt', ["p1=^|please", "n1=@IMPN"]),
        ('pɹəʤˈɛkt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('pɹəʤˈɛkt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('pɹəʤˈɛkt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('pɹəʤˈɛkt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'putting': [
        ('pˈʌɾɪŋ', ["p1=his|her|my|your|their|our|the|whose", "n1!=@OBJ|up|on|off|out|away|down|in|together|back|it|them|forward|aside|through"]),
    ],
    'rebel': [
        ('', ["p1=^", "N=rebel|rebels"]),
        ('', ["p2=rebel|rebels", "p3=^"]),
        ('ɹˈɛbᵊl', ["p1=@DETN", "n1!=@DETX"]),
        ('ɹᵻbˈɛl', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɹᵻbˈɛl', ["p1=@SUBJX"]),
        ('ɹᵻbˈɛl', ["p1=^|please", "n1=@IMPN"]),
        ('ɹᵻbˈɛl', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɹᵻbˈɛl', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɹᵻbˈɛl', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɹᵻbˈɛl', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'record': [
        ('', ["p1=^", "N=record|records"]),
        ('', ["p2=record|records", "p3=^"]),
        ('ɹˈɛkəɹd', ["p1=@DETN", "n1!=@DETX"]),
        ('ɹᵻkˈɔɹd', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɹᵻkˈɔɹd', ["p1=@SUBJX"]),
        ('ɹᵻkˈɔɹd', ["p1=^|please", "n1=@IMPN"]),
        ('ɹᵻkˈɔɹd', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɹᵻkˈɔɹd', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɹᵻkˈɔɹd', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɹᵻkˈɔɹd', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'refuse': [
        ('ɹˈɛfjus', ["p1=of|household|kitchen|garden|industrial|domestic|municipal|human|toxic", "n1!=to|@OBJ"]),
        ('ɹˈɛfjus', ["p1=the", "n1!=to|@OBJ|@SUBJX"]),
        ('', ["p1=^", "N=refuse|refuses"]),
        ('', ["p2=refuse|refuses", "p3=^"]),
        ('ɹˈɛfjus', ["p1=@DETN", "n1!=@DETX"]),
        ('ɹᵻfjˈuz', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('ɹᵻfjˈuz', ["p1=@SUBJX"]),
        ('ɹᵻfjˈuz', ["p1=^|please", "n1=@IMPN"]),
        ('ɹᵻfjˈuz', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('ɹᵻfjˈuz', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('ɹᵻfjˈuz', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('ɹᵻfjˈuz', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'resume': [
        ('ɹˈɛzumˌA', ["p1=@DETN|updated|polished|strong|attach|send|submit|upload|email|new|current|one-page|two-page"]),
    ],
    'row': [
        ('ɹˈW', ["p1=a|the|huge|big|blazing|furious|bitter|public|family|another|political|diplomatic|major|heated|massive", "n1=in|over|about|with|between|erupted|broke|has|had|after|among|within|that"]),
    ],
    'résumé': [
        ('ɹˈɛzumˌA', []),
    ],
    'separate': [
        ('sˈɛpɹət', ["p1=@DETN", "n1!=@DETX"]),
        ('sˈɛpɹət', ["p1=@BE|very|more|most|less|quite|so|too|perfectly|entirely|completely|fully|highly|rather|not|seem|seems|seemed|look|looks|looked|feel|feels|felt|become|became"]),
        ('sˈɛpəɹɹˌAt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('sˈɛpəɹɹˌAt', ["p1=@SUBJX"]),
        ('sˈɛpəɹɹˌAt', ["p1=^|please", "n1=@IMPN"]),
        ('sˈɛpəɹɹˌAt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('sˈɛpəɹɹˌAt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('sˈɛpəɹɹˌAt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
    ],
    'sewer': [
        ('sˈOəɹ', ["P=skilled|talented|expert|experienced|keen|avid|amateur|seamstress"]),
        ('sˈOəɹ', ["N=quilting|sewing|clothes|fabric|quilts|quilt|dresses|stitch|stitches|thread|needle|patterns|seams|hems"]),
    ],
    'sow': [
        ('sˈW', ["p1=@DETN|prize|pregnant|old|breeding|fat", "n1!=@DETX|seeds|seed|the"]),
    ],
    'subject': [
        ('', ["p1=^", "N=subject|subjects"]),
        ('', ["p2=subject|subjects", "p3=^"]),
        ('sˈʌbʤɛkt', ["p1=@DETN", "n1!=@DETX"]),
        ('səbʤˈɛkt', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('səbʤˈɛkt', ["p1=@SUBJX"]),
        ('səbʤˈɛkt', ["p1=^|please", "n1=@IMPN"]),
        ('səbʤˈɛkt', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('səbʤˈɛkt', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('səbʤˈɛkt', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('səbʤˈɛkt', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'survey': [
        ('', ["p1=^", "N=survey|surveys"]),
        ('', ["p2=survey|surveys", "p3=^"]),
        ('sˈɜɹvA', ["p1=@DETN", "n1!=@DETX"]),
        ('səɹvˈA', ["p1=@MODAL|@DO|to|please|let's|let"]),
        ('səɹvˈA', ["p1=@SUBJX"]),
        ('səɹvˈA', ["p1=^|please", "n1=@IMPN"]),
        ('səɹvˈA', ["p2=@MODAL|@DO|to", "p1=@ADV|@SUBJX|all|both"]),
        ('səɹvˈA', ["p1~s", "p1!~'s|ss|us|is|ous|ics|ness", "p1!=@NOTPL|@DETN|@BE|@HAVE|@PREP|@ADV", "n1!=of|is|was|are|were|and|or|$|to|for|that|which|who|in|on|at|with|by|as|but|has|had|have|will|would"]),
        ('səɹvˈA', ["P=@MODAL|@DO", "p1~s", "n1=$"]),
        ('səɹvˈA', ["p1=often|sometimes|always|never|usually|rarely|seldom|also|frequently|regularly|occasionally|routinely"]),
    ],
    'tear': [
        ('tˈɛɹ', ["p1=and", "p2=wear"]),
        ('tˈɛɹ', ["p1=^|please|to|@MODAL|@DO|@SUBJX|not", "n1=@OBJ|along|up|down|off|apart|open|out|through|into|at"]),
        ('tˈɛɹ', ["p1=acl|muscle|ligament|meniscus|rotator|hamstring|tendon|cartilage|retinal"]),
        ('tˈɛɹ', ["p1=a|the|small|tiny|big|large|minor|long|little", "n1=in|on|at", "N=shirt|jeans|fabric|sleeve|paper|tent|sail|seam|pants|dress|sheet|muscle|ligament|cartilage|knee|meniscus|tendon|bag|screen|upholstery|canvas|coat|jacket|sock|glove|lining|skin"]),
    ],
    'tears': [
        ('tˈɛɹz', ["p1=small|tiny|big|large|minor|long|several|little|multiple|muscle|ligament|any", "N!=eyes|joy|of|streamed|streaming|rolled|ran|welled|flowed"]),
        ('tˈɛɹz', ["p1=@SUBJX|it|and|then|never|always|just|carefully|quickly", "n1=@OBJ|open|up|down|off|apart|into|through|out|at"]),
    ],
    'upset': [
        ('ˈʌpsɛt', ["p1=@DETN|biggest|major|huge|stunning|big|shocking|surprise|massive|historic|minor|first-round", "n1!=@DETX|me|him|her|them|us|you|it|about|that|with|by|when|stomach"]),
    ],
    'used': [
        ('jˈust', ["n1=to", "p1=@BE|get|got|gets|getting|become|became|grew", "n2~ing|@DETX|it|this|that|them|him|her|me|us|being|having"]),
        ('jˈust', ["n1=to", "p1=@SUBJX|it|never|always|once|not|also|just|people|there|things|we|they"]),
    ],
}
# HOMOGRAPHS-END


def hg_set(v: str) -> set[str]:
    out: set[str] = set()
    for x in v.split("|"):
        out |= set(HG_CLASSES[x[1:]].split()) if x.startswith("@") else {x}
    return out


_HG_SETS: dict[str, set[str]] = {}


def hg_test(t: str, prev: list[str], nxt: list[str], cap: bool) -> bool:
    if t == "cap":
        return cap
    if t == "!cap":
        return not cap
    for op in ("!=", "!~", "=", "~"):
        k = t.find(op)
        if k > 0:
            break
    field, vals = t[:k], t[k + len(op):]
    if field in ("P", "N"):
        ws = [w for w in (prev if field == "P" else nxt) if w not in ("^", "$")] or [prev[-1] if field == "P" else nxt[-1]]
    else:
        seq = prev if field[0] == "p" else nxt
        n = int(field[1]) - 1
        ws = [seq[n] if n < len(seq) else seq[-1]]
    if op in ("~", "!~"):
        ends = vals.split("|")
        hit = any(w not in ("^", "$") and any(w.endswith(e) for e in ends) for w in ws)
        return hit if op == "~" else not hit
    s = _HG_SETS.get(vals)
    if s is None:
        s = _HG_SETS[vals] = hg_set(vals)
    hit = any(w in s for w in ws)
    return not hit if op == "!=" else hit


OPEN = "\"'“‘([{«"
CLOSE = "\"'”’)]}»,.!?;:…"


USER_FORMAT = "leokani-g2p-user/1"
SIBILANT_END = set("szʃʒʧʤ")
VOICELESS_END = set("ptkfθ")


class UserLexicon:
    """Custom pronunciations (brands, people, places), checked before the lexicon and before any normaliser rule.

    A value is phonemes (written /like this/ in files, or {"phonemes": ...}) or a respelling (plain text, or
    {"say": ...}) that is then read as written text. Keys are single tokens. A key with no capital letter matches
    any casing; a key with a capital matches only that casing, and wins. "Leokani's" falls back to "Leokani"
    (phonemes + ᵻz/s/z, or the respelling + 's); "James'" to "James" with nothing added. The format is shared by
    every port: product/data/leokani-g2p-user-lexicon.schema.json and USER-LEXICON.md."""

    def __init__(self, entries=None, symbols: set[str] | None = None):
        self.symbols = symbols                              # allowed phoneme symbols (None: no check)
        self.exact: dict[str, tuple[str, str]] = {}         # key with a capital -> (kind, value)
        self.lower: dict[str, tuple[str, str]] = {}         # all-lowercase key
        if entries:
            self.update(entries)

    def __len__(self) -> int:
        return len(self.exact) + len(self.lower)

    @staticmethod
    def parse(value) -> tuple[str, str]:
        if isinstance(value, dict):
            if set(value) == {"phonemes"}:
                kind, val = "phonemes", value["phonemes"]
            elif set(value) == {"say"}:
                kind, val = "say", value["say"]
            else:
                raise ValueError(f"an entry is {{\"phonemes\": ...}} or {{\"say\": ...}}, not {value!r}")
        elif isinstance(value, str):
            v = value.strip()
            if len(v) >= 2 and v[0] == "/" and v[-1] == "/":
                kind, val = "phonemes", v[1:-1]
            else:
                kind, val = "say", v
        else:
            raise ValueError(f"not a pronunciation: {value!r}")
        val = " ".join(val.split())
        if not val:
            raise ValueError("an empty pronunciation")
        return kind, val

    def add(self, word: str, value=None, *, phonemes: str | None = None, say: str | None = None) -> None:
        """add("Leokani", "/lˌAOkˈɑni/"), add("Siobhan", say="shivawn"), add("gif", phonemes="ʤˈɪf")."""
        if (value is None) + (phonemes is None) + (say is None) != 2:
            raise ValueError("give exactly one of value, phonemes= or say=")
        kind, val = self.parse(value if value is not None else
                               {"phonemes": phonemes} if phonemes is not None else {"say": say})
        key = word.strip().replace("’", "'")
        key = Normalizer.split(key)[1] or key                # matched against a token's core: "Mx." -> "Mx"
        if not key or any(c.isspace() for c in key):
            raise ValueError(f"a key is one token with no spaces: {word!r}")
        if kind == "phonemes" and self.symbols is not None:
            bad = sorted({c for c in val if c != " " and c not in self.symbols})
            if bad:
                raise ValueError(f"{word}: unknown phoneme symbols {' '.join(bad)}")
        (self.exact if key != key.lower() else self.lower)[key] = (kind, val)

    def update(self, entries) -> None:
        if isinstance(entries, UserLexicon):
            self.exact.update(entries.exact)
            self.lower.update(entries.lower)
            return
        if isinstance(entries, dict) and "words" in entries and "format" in entries:
            if entries["format"] != USER_FORMAT:
                raise ValueError(f"not a {USER_FORMAT} file: {entries['format']!r}")
            entries = entries["words"]
        if not isinstance(entries, dict):
            raise ValueError("a user lexicon is an object: word -> pronunciation")
        for k, v in entries.items():
            self.add(k, v)

    def load(self, path: str) -> "UserLexicon":
        """Add the entries of a .json file (the schema) or a .tsv file (key TAB value, # comments)."""
        with open(path, encoding="utf-8") as f:
            text = f.read()
        if path.lower().endswith(".json"):
            self.update(json.loads(text))
            return self
        for n, ln in enumerate(text.splitlines(), 1):
            ln = ln.strip().lstrip("\ufeff")
            if not ln or ln.startswith("#"):
                continue
            if "\t" not in ln:
                raise ValueError(f"{path}:{n}: expected key<TAB>value")
            k, v = ln.split("\t", 1)
            try:
                self.add(k, v)
            except ValueError as e:
                raise ValueError(f"{path}:{n}: {e}") from None
        return self

    def get(self, core: str) -> tuple[str, str] | None:
        c = core.replace("’", "'")
        return self.exact.get(c) or self.lower.get(c.lower())

    def rewrite(self, core: str) -> tuple[str, str] | None:
        """A token's core -> ("phonemes", ph) or ("say", text), possessives included, or None."""
        hit = self.get(core)
        if hit is not None:
            return hit
        c = core.replace("’", "'")
        if len(c) > 2 and c[-2:] in ("'s", "'S"):
            hit = self.get(c[:-2])
            if hit is None:
                return None
            kind, val = hit
            if kind == "say":
                return kind, val + "'s"
            last = val.replace(PRIMARY, "").replace(SECONDARY, "").rstrip()[-1:]
            return kind, val + ("ᵻz" if last in SIBILANT_END else "s" if last in VOICELESS_END else "z")
        if len(c) > 2 and c[-1] == "'" and c[-2] in "sS":
            return self.get(c[:-1])
        return None


class Normalizer:
    """Rewrites a line so the G2P reads it as a person would: money, phone numbers, times and dates, emails, URLs
    and handles, versions and IP addresses, units, fractions, ratios and ranges, Roman numerals, abbreviations,
    a few heteronyms and names. Plain words pass through untouched, so ordinary text gives exactly what it gave
    before. pauses=False (inside a piece) leaves out the commas it would put between phone-number groups."""

    TIME = re.compile(r"^(\d{1,2}):(\d{2})(?::(\d{2}))?(?:([ap])\.?m\.?)?$", re.I)
    TIME_AMPM = re.compile(r"^(\d{1,2})([ap])\.?m\.?$", re.I)
    EMAIL = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._%+-]*)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)$")
    URL = re.compile(r"^(?:(https?|ftp)://)?((?:[A-Za-z0-9-]+\.)+[A-Za-z]{2,})(/\S*)?$", re.I)
    MONEY = re.compile(r"^(-?)([$€£¥₹])(\d[\d,]*)?(\.\d+)?(k|K|m|M|mm|b|B|bn|t|T)?$")
    CENTS = re.compile(r"^(\d+)¢$")
    PHONE = re.compile(r"^(?:(\+?1)[-. ])?\(?(\d{3})\)?[-.](\d{3})[-.](\d{4})$")
    PHONE7 = re.compile(r"^(\d{3})-(\d{4})$")
    TOLLWORD = re.compile(r"^1-(\d{3})-([A-Za-z]{3,})$")
    IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")
    VERSION = re.compile(r"^([vV])?(\d+(?:\.\d+)+)([-+][A-Za-z0-9.]+)?$")
    VERSION_DASH = re.compile(r"^(\d+(?:\.\d+){2,})((?:-[A-Za-z0-9.]+){2,})$")
    DECADE = re.compile(r"^['’]?(\d{2}|\d{4})s$")
    DATE_MDY = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{2}|\d{4})$")
    DATE_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
    FRACTION = re.compile(r"^(\d{1,3})/(\d{1,3})$")
    RANGE = re.compile(r"^(\d[\d,]*(?:\.\d+)?)[-–](\d[\d,]*(?:\.\d+)?)$")
    TIMES_X = re.compile(r"^(\d+)[x×](\d+)$")
    MULT = re.compile(r"^(\d+(?:\.\d+)?)[x×]$")
    RATIO = re.compile(r"^(\d{1,2}):(\d)$")
    DIGITS = re.compile(r"^\d{13,}$")
    LEADING_POINT = re.compile(r"^\.(\d+)$")
    DEGREES = re.compile(r"^(-?\d[\d,]*(?:\.\d+)?)°([CF])?$")

    def __init__(self, known=None, letters: dict[str, str] | None = None, cased=None, common=None, reading=None):
        self.reading = reading or (lambda w: [])            # the lexicon's base and forms for a lowercase word
        self.cased = cased or (lambda w: False)              # a capitalised form the lexicon keeps as written
        self.common = common or (lambda w: False)            # one of the context model's frequent words
        lexicon = known or (lambda w: False)
        self.known = lambda w: w in SAY_AS or lexicon(w)    # is w a word the lexicon (or SAY_AS) has
        self.letters = letters or {}                        # letter name phonemes, "a" -> ˈA
        self.user: UserLexicon | None = None                # custom pronunciations, checked before any rule
        self._user_on = True

    # ---- helpers
    def spelled(self, w: str) -> bool:
        """The lexicon already says w letter by letter, as its base or one of its forms (or doesn't have it)."""
        forms = self.reading(w)
        bare = lambda x: x.replace(PRIMARY, "").replace(SECONDARY, "").replace(" ", "")  # noqa: E731
        letters = "".join(bare(self.letters.get(c, "?")) for c in w)
        return not forms or any(bare(f) == letters for f in forms)

    def letter(self, c: str) -> str:
        ph = self.letters.get(c.lower())
        return f"{c.upper()}{PH}{ph}" if ph else c.upper()

    def spell(self, s: str) -> list[str]:
        return [self.letter(c) if c.isalpha() else ONES[int(c)] for c in s if c.isalnum() and c.isascii()]

    def spell_word(self, s: str, end: str = "") -> list[str]:
        """An initialism said as one word, stress on the last letter ("NBA"); end is a plural or
        possessive ("IDs", "AGC's")."""
        names = [self.letters.get(c.lower()) for c in s]
        if not s.isalpha() or not s.isascii() or any(n is None for n in names):
            return self.spell(s)
        last = self.letter_plural(s[-1], "" if end == "s" else end).split(PH, 1)[1] if end else names[-1]
        return [f"{s}{end}{PH}" + "".join(n.replace(PRIMARY, SECONDARY) for n in names[:-1]) + last]

    def segment(self, run: str) -> list[str] | None:
        """A run of letters written as one ('milliwattlabs') split into lexicon words, fewest pieces first."""
        low = run.lower()
        n = len(low)
        best: list[list[str] | None] = [None] * (n + 1)
        best[0] = []
        for i in range(1, n + 1):
            for j in range(max(0, i - 20), i):
                w = low[j:i]
                if best[j] is None or not (len(w) >= 3 or (j == 0 and len(w) == 1 and i < n)):
                    continue
                if len(w) > 1 and not self.known(w):
                    continue
                cand = best[j] + [w]
                if best[i] is None or len(cand) < len(best[i]):
                    best[i] = cand
        out = best[n]
        return out if out and len(out) > 1 else None

    def say_run(self, run: str) -> list[str]:
        """One alphanumeric run of an email, a URL or a handle."""
        out = []
        for m in re.finditer(r"[A-Za-z]+|\d+", run):
            g = m.group()
            if g.isdigit():
                out += digit_words(g)
            elif self.known(g.lower()):
                out.append(self.word(g.lower()))
            elif self.segment(g):
                out += [self.letter(w) if len(w) == 1 else self.word(w) for w in self.segment(g)]
            elif len(g) > 3 and re.search(r"[aeiouy]", g.lower()):
                out.append(g.lower())                        # a name: the letter-to-sound model
            else:
                out += self.spell(g)
        return out

    @staticmethod
    def word(w: str) -> str:
        return w + PH + SAY_AS[w] if w in SAY_AS else w

    def say_parts(self, s: str) -> list[str]:
        out = []
        for part in re.split(r"([._+\-/~=?&#:%])", s):
            if not part:
                continue
            if part in SEP_WORDS:
                out.append(SEP_WORDS[part])
            else:
                out += self.say_run(part)
        return out

    def domain(self, d: str) -> list[str]:
        labels = d.split(".")
        out = []
        for i, lab in enumerate(labels):
            if i:
                out.append("dot")
            low = lab.lower()
            if i == len(labels) - 1 and low in TLDS:
                out += [TLD_SAY[low]] if low in TLD_SAY else self.spell(low)
            elif low == "www":
                out += self.spell("www")
            else:
                out += self.say_parts(lab)
        return out

    @staticmethod
    def amount(s: str) -> list[str]:
        return [s]                                           # the number reader says digits as espeak does

    def money(self, sign: str, cur: str, whole: str | None, frac: str | None, scale: str | None,
              next_scale: str | None) -> list[str]:
        one, many, cent, cents = CURRENCY[cur]
        out = ["minus"] if sign else []
        whole = whole or "0"
        n = int(whole.replace(",", "") or 0)
        sc = SCALES.get(scale or "") or next_scale
        if sc:
            return out + [whole + (frac or ""), sc, many]
        if frac and len(frac) == 3 and cents:
            c = int(frac[1:])
            if n == 0 and c:
                return out + [str(c), cent if c == 1 else cents]
            if c == 0:
                return out + [whole, one if n == 1 else many]
            if cur == "£":
                return out + [whole, one if n == 1 else many, str(c)]
            return out + [whole, one if n == 1 else many, "and", str(c), cent if c == 1 else cents]
        if frac:
            return out + [whole + frac, many]
        return out + [whole, one if n == 1 and cur not in "¥" else many]

    def phone(self, groups: list[str], pauses: bool, plus: bool = False) -> list[str]:
        out = ["plus"] if plus else []
        for i, g in enumerate(groups):
            w = digit_words(g) if g.isdigit() else [g.lower()]
            if g == "800" and i == 1 and groups[0] == "1":
                w = ["eight", "hundred"]                     # 1-800: "one eight hundred"
            if pauses and i < len(groups) - 1:
                w[-1] += ","
            out += w
        return out

    def time(self, h: str, m: str, s: str | None, ampm: str | None) -> list[str] | None:
        hh, mm = int(h), int(m)
        if hh > 24 or mm > 59:
            return None
        if s is not None:
            ss = int(s)
            if ss > 59:
                return None
            out = [str(hh)] + (["oh", str(mm)] if 0 < mm < 10 else [m] if mm else ["hundred"])
            return out + (["oh", str(ss)] if 0 < ss < 10 else [s] if ss else ["hundred"])
        out = [str(hh)]
        if mm == 0:
            out += ["hundred"] if hh >= 13 or (h.startswith("0") and not ampm) else []
        elif mm < 10:
            out += ["oh", str(mm)]
        else:
            out += [m]
        if ampm:
            out += [self.letter(ampm), "M"]
        return out

    @staticmethod
    def fraction(n: int, d: int) -> list[str] | None:
        names = {2: ("half", "halves"), 4: ("quarter", "quarters")}
        if d in names:
            one, many = names[d]
        elif d in (3, 5, 6, 7, 8, 9, 10, 12, 16, 32, 64, 100):
            one = ordinal(d)
            many = one + "s"
        else:
            return None
        if not 0 < n < d:
            return None
        return [cardinal(n), one if n == 1 else many]

    # ---- the line
    VULGAR = {"½": "1/2", "¼": "1/4", "¾": "3/4", "⅓": "1/3", "⅔": "2/3", "⅛": "1/8", "⅜": "3/8", "⅝": "5/8",
              "⅞": "7/8"}
    NAMED_RANGE = re.compile(r"(?<=\w)([–—])(?=(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Mon|Tue|Wed|Thu|"
                             r"Fri|Sat|Sun)[a-z]*\.?\b)")

    VULGAR_WORDS = {"½": "a half", "¼": "a quarter", "¾": "three quarters", "⅓": "a third", "⅔": "two thirds",
                    "⅛": "an eighth", "⅜": "three eighths", "⅝": "five eighths", "⅞": "seven eighths"}

    def __call__(self, text: str, pauses: bool = True) -> str:
        text = text.replace("\u2011", "-").replace("\u2010", "-")
        # "1 ½" is a mixed number ("one and a half"); a lone "½ cup" is "a half cup", as espeak says it
        text = re.sub(r"(\d)\s*([" + "".join(self.VULGAR) + "])", lambda m: m.group(1) + " " + self.VULGAR[m.group(2)] + " ",
                      text)
        text = re.sub("|".join(self.VULGAR), lambda m: " " + self.VULGAR_WORDS[m.group()] + " ", text)
        text = self.NAMED_RANGE.sub(" \\1 ", text)
        toks = text.split()
        out: list[str] = []
        i = 0
        while i < len(toks):
            words, used = self.token(toks, i, pauses)
            out.extend(words)
            i += used
        return " ".join(out)

    @staticmethod
    def split(t: str) -> tuple[str, str, str]:
        a = 0
        while a < len(t) and t[a] in OPEN and not re.match(r"^['’]\d0s", t[a:]):
            a += 1
        b = len(t)
        while b > a and t[b - 1] in CLOSE:
            b -= 1
        return t[:a], t[a:b], t[b:]

    def token(self, toks: list[str], i: int, pauses: bool) -> tuple[list[str], int]:
        t = toks[i]
        if PH in t:
            return [t], 1
        lead, core, trail = self.split(t)
        user = self.user.rewrite(core) if self.user is not None and self._user_on and core else None
        if user is not None:                                 # a custom pronunciation, before any rule
            kind, val = user
            if kind == "phonemes":
                words = [core + PH + val]
            else:
                self._user_on = False                        # a respelling's words are not looked up again
                try:
                    words = [w for w in self(val, pauses).split(" ") if w]
                finally:
                    self._user_on = True
            return self._finish(words, 1, lead, core, trail)
        prev = self.split(toks[i - 1])[1] if i else ""
        prev_end = i == 0 or toks[i - 1][-1:] in ".!?:;"   # this word starts a sentence or clause
        prev2 = self.split(toks[i - 2])[1].lower() if i > 1 else ""
        nxt_raw = toks[i + 1] if i + 1 < len(toks) else ""
        nxt = self.split(nxt_raw)[1]
        try:
            res = self.rewrite(core, trail, prev, prev2, prev_end, nxt, nxt_raw, toks, i, pauses)
        except (ValueError, KeyError, IndexError, TypeError, AttributeError, RecursionError):
            res = None                                       # never fail a line: keep the token as written
        if res is None:
            return [t], 1
        words, used, trail = res
        return self._finish(words, used, lead, core, trail)

    @staticmethod
    def _finish(words, used, lead, core, trail):
        if "(" in lead and ")" not in trail and (used > 1 or ")" in core):
            lead = lead.replace("(", "")                     # "(555) 867-5309": the bracket closed inside
        if not words:
            return ([lead.strip("\"'“‘([{«") + trail] if trail.strip("\"'”’)]}»") else []), used
        words = [part for w in words for part in
                 ([w] if PH not in w or " " not in w else [w.split(PH)[0] + PH + p for p in w.split(PH, 1)[1].split(" ")])]
        words[0] = lead + words[0]
        words[-1] = words[-1] + trail
        return words, used

    def rewrite(self, core, trail, prev, prev2, prev_end, nxt, nxt_raw, toks, i, pauses):
        """-> (words, tokens used, trailing punctuation) or None to keep the token as written."""
        if not core:
            return None
        for rules in (self.letters_first, self.more2, self.more, self.more3):
            res = rules(core, trail, prev, prev2, nxt, nxt_raw, toks, i, pauses)
            if res is not None:
                return res
        res = self.basic(core, trail, prev, prev2, prev_end, nxt, nxt_raw, toks, i, pauses)
        return res if res is not None else self.capitals(core, trail, prev, nxt, toks, i)

    def sub(self, text: str, pauses: bool) -> list[str]:
        return self(text, pauses).split(" ")

    def more(self, core, trail, prev, prev2, nxt, nxt_raw, toks, i, pauses):
        """Second-round rules (the held-out batch): compounds, money per unit, years, addresses, phones, versions."""
        low, pl, nl = core.lower(), prev.lower(), nxt.lower()
        is_num = lambda x: bool(re.match(r"^-?\d[\d,]*(\.\d+)?$", x))  # noqa: E731
        # a range or compound written with a dash: "3pm-5pm", "$5M-$7M", "10am–noon", "3-for-$10"
        if re.search(r"[–—-]", core) and re.search(r"\d", core) and not self.PHONE.match(core) \
                and not self.TOLLWORD.match(core) and not re.match(r"^[\d,.]+([–-][\d,.]+)+$", core) \
                and not self.DATE_ISO.match(core) and not self.VERSION_DASH.match(core) \
                and not re.match(r"^\d{1,2}:\d{2}[-–]\d{1,2}:\d{2}$", core):
            parts = re.split(r"[–—-]", core)
            timey = lambda p: bool(self.TIME.match(p) or self.TIME_AMPM.match(p) or p.lower() in ("noon", "midnight"))  # noqa: E731
            money = lambda p: bool(self.MONEY.match(p))  # noqa: E731
            if len(parts) == 2 and all(parts) and (all(timey(p) for p in parts) or all(money(p) for p in parts)):
                a, b = self.sub(parts[0], pauses), self.sub(parts[1], pauses)
                if money(parts[0]) and a[-1] == b[-1]:
                    a = a[:-1]                                   # "5 million to 7 million dollars"
                return a + ["to"] + b, 1, trail
            if all(parts) and any(money(p) or self.TIME_AMPM.match(p) for p in parts):
                out = []
                for p in parts:
                    out += self.sub(p, pauses)
                return out, 1, trail
        # money per unit: "£2,450/month", "$12/hr"
        m = re.match(r"^([$€£¥₹][\d,.]+[kKmMbB]?)/([A-Za-z]+)$", core)
        if m and m.group(2).lower() in PER_UNIT:
            return self.sub(m.group(1), pauses) + PER_UNIT[m.group(2).lower()].split(" "), 1, trail
        # money said as a modifier: "a $100 gift card", "£5 notes"
        m = self.MONEY.match(core)
        if m and m.group(3) and not m.group(4) and not m.group(5) and nl in ATTRIBUTIVE:
            return (["minus"] if m.group(1) else []) + [m.group(3), CURRENCY[m.group(2)][0]], 1, trail
        # phone pieces: "(212)555-0100", extensions, star codes, pound
        m = re.match(r"^\(?(\d{3})\)(\d{3})-(\d{4})$", core)
        if m:
            return self.phone(list(m.groups()), pauses), 1, trail
        m = re.match(r"^(?:x|ext\.?)(\d{1,5})$", core, re.I)
        if m:
            d = m.group(1)
            return ["extension"] + (digit_words(d) if len(d) > 2 else [d]), 1, trail
        if low == "ext" and trail.startswith(".") and nxt[:1].isdigit():
            return ["extension"], 1, trail[1:]
        m = re.match(r"^\*(\d{1,4})#?$", core)
        if m:
            return ["star"] + digit_words(m.group(1)) + (["pound"] if core.endswith("#") else []), 1, trail
        if core == "#" and (pl in ("press", "then", "hit", "dial", "enter", "and", "or") or not nxt):
            return ["pound"], 1, trail
        if core == "*" and not (is_num(prev) and is_num(nxt)):
            return ["star"], 1, trail
        # military time: "0800 hours"
        if re.match(r"^[0-2]\d[0-5]\d$", core) and nl in ("hours", "hrs", "hr", "h"):
            h, mm = int(core[:2]), int(core[2:])
            return (["oh"] if core[0] == "0" else []) + [cardinal(h)] + (
                ["hundred"] if mm == 0 else ["oh", ONES[mm]] if mm < 10 else [cardinal(mm)]), 1, trail
        # web: "localhost:8080/v1/chat", "ftp://files.example.net"
        m = re.match(r"^(?:https?://)?(localhost|(?:[\w-]+\.)+[a-z]{2,}|\d{1,3}(?:\.\d{1,3}){3}):(\d{2,5})(/\S*)?$", core)
        if m:
            host, port = m.group(1), m.group(2)
            words = (self.ip(host) if self.IPV4.match(host) else ["local", "host"] if host == "localhost"
                     else self.domain(host))
            words += ["colon"] + (pair_words(int(port)) if len(port) == 4 and port[1:] != "000" and int(port) < 2100
                                  else [port[:2], port[2:]] if len(port) == 4 and port[2] != "0" and port[1:] != "000"
                                  else [port])
            for seg in (m.group(3) or "").split("/")[1:]:
                words += ["slash"] + (self.say_parts(seg) if seg else [])
            return words, 1, trail
        if low.startswith("ftp://") and len(core) > 6:
            return self.spell("FTP") + ["colon", "slash", "slash"] + self.sub(core[6:], pauses), 1, trail
        # versions: "Python 3.12", "1.10", "v20.x", "6.8.0-45-generic", build "23A344"
        m = re.match(r"^([vV])?(\d+)\.(\d{2,3}|x)$", core)
        if m and (pl in VERSION_CUE or m.group(1) or m.group(3) == "x" or
                  (m.group(3).endswith("0") and not m.group(3).startswith("0") and nl not in UNITS
                   and not is_num(prev) and pl not in ("is", "of", "at", "was", "by", "about", "gpa", "score"))):
            minor = [self.letter("x")] if m.group(3) == "x" else [m.group(3)]
            return (["version"] if m.group(1) else []) + [m.group(2), "point"] + minor, 1, trail
        m = self.VERSION_DASH.match(core)
        if m:
            words = []
            for k, x in enumerate(m.group(1).split(".")):
                words += (["point"] if k else []) + [x]
            for part in m.group(2).split("-")[1:]:
                words += ["dash"] + (self.sub(part, pauses) if part else [])
            return words, 1, trail
        if re.match(r"^\d+[A-Z]+\d+[A-Z0-9]*$", core) and len(core) >= 4:
            words = []
            for g in re.findall(r"\d+|[A-Z]+", core):
                words += ([g] if len(g) <= 2 else digit_words(g)) if g.isdigit() else self.spell(g)
            return words, 1, trail
        # hex strings: say every character
        if len(core) >= 8 and re.match(r"^[0-9a-fA-F]+$", core) and re.search(r"\d", core) and \
                re.search(r"[a-fA-F]", core):
            return self.spell(core), 1, trail
        # digit groups in a run (card, account and IBAN numbers): digit by digit
        if re.match(r"^\d{2,4}$", core):
            near = [self.split(t)[1] for t in toks[max(0, i - 2):i + 3]]
            if sum(bool(re.match(r"^(\d{4}|[A-Z]{2}\d{2})$", t)) for t in near) >= 3:
                w = digit_words(core)
                if pauses and not trail and i + 1 < len(toks):
                    w[-1] += ","
                return w, 1, trail
        if re.match(r"^[A-Z]{2}\d{2}$", core) and re.match(r"^\d{4}$", nxt):
            w = self.spell(core[:2]) + digit_words(core[2:])
            if pauses and not trail:
                w[-1] += ","
            return w, 1, trail
        # years after a month or a day: "Dec. 1999", "March 14, 1988", "the 31st of December 1999"
        if re.match(r"^1[1-9]\d\d$", core) and not core.endswith("00") and i and (
                prev in MONTHS or (pl in MONTH_ABBR and prev[:1].isupper()) or
                re.match(r"^\d{1,2}(st|nd|rd|th)?,$", toks[i - 1]) or
                re.match(r"^(\w+ )?\w+(st|nd|rd|th),$", toks[i - 1])):
            return year_words(int(core)), 1, trail
        # a day after a month is an ordinal ("July 5" -> July fifth); a day before one is "the fifth of July"
        if re.match(r"^\d{1,2}$", core) and 1 <= int(core) <= 31 and (prev in MONTHS or
                                                                    (pl in MONTH_ABBR and prev[:1].isupper())):
            if nl not in UNITS and nl not in ("percent", "degrees", "hours", "minutes", "days", "people", "times"):
                return [ordinal(int(core))], 1, trail
        if re.match(r"^\d{1,2}$", core) and 1 <= int(core) <= 31 and nxt in MONTHS and pl not in ("the", "of") \
                and not is_num(prev):
            return ["the", ordinal(int(core)), "of"], 1, trail
        # addresses
        if low in DIRECTIONS and core.isupper():
            if len(core) == 2 and (pl.rstrip(".") in STREET_WORDS or prev in STREET_ABBR.values()):
                return [DIRECTIONS[low]], 1, trail
            if len(core) == 1 and trail.startswith(".") and (nxt[:1].isupper() or
                                                              re.match(r"^\d+(st|nd|rd|th)$", nxt)):
                return [DIRECTIONS[low]], 1, trail[1:]
        if low in ("ste", "hwy", "rte", "ave", "blvd") and core[0].isupper() and \
                (nxt[:1].isdigit() or low in ("ave", "blvd") and prev[:1].isupper()):
            word = {"ste": "Suite", "hwy": "Highway", "rte": "Route", "ave": "Avenue", "blvd": "Boulevard"}[low]
            if trail.startswith(".") and (len(trail) > 1 or (nxt and not nxt[:1].isupper())):
                trail = trail[1:]
            return [word], 1, trail
        if core in STATES and re.match(r"^\d{5}(-\d{4})?$", nxt) and i and toks[i - 1].endswith(","):
            z = self.split(nxt_raw)
            return STATES[core].split(" ") + digit_words(z[1]), 2, z[2]
        m = re.match(r"^I-(\d{1,3})$", core)
        if m:
            d = m.group(1)
            return [self.letter("I")] + ([d] if len(d) <= 2 else [ONES[int(d[0])]] +
                                         (["oh", ONES[int(d[2])]] if d[1] == "0" else [d[1:]])), 1, trail
        if re.match(r"^[1-9]\d{3}$", core) and (pl in ("box", "suite", "ste", "room", "unit", "apt", "apartment")
                                              or nxt[:1].isupper() and any(
                                                  self.split(t)[1].lower().rstrip(".") in STREET_WORDS
                                                  for t in toks[i + 1:i + 4])):
            return pair_words(int(core)), 1, trail
        # feet and inches, scientific notation, a unit after a hyphen
        inch = trail[:1] != "" and trail[:1] in "\"”″"
        m = re.match(r"^(\d{1,2})[′'’](\d{1,2})$", core)
        if m and inch:
            return [m.group(1), "foot", m.group(2)], 1, trail[1:]
        if re.match(r"^\d+(\.\d+)?$", core) and inch and (prev in ("a", "an", "the") or nl in ("bolt", "screw", "pipe",
                                                                                            "screen", "display",
                                                                                            "tv", "monitor", "wide",
                                                                                            "long", "tall", "deep",
                                                                                            "thick", "of", "nail")):
            return [core, "inch" if core == "1" or prev in ("a", "an", "the") else "inches"], 1, trail[1:]
        m = re.match(r"^(\d{1,3})/(\d{1,3})$", core)
        if m and inch and self.fraction(int(m.group(1)), int(m.group(2))):
            return self.fraction(int(m.group(1)), int(m.group(2))) + ["inch"], 1, trail[1:]
        m = re.match(r"^(-?\d+(?:\.\d+)?)[eE]([-+]?)(\d{1,3})$", core)
        if m:
            sign = ["minus"] if m.group(2) == "-" else []
            return [m.group(1), "times", "ten", "to", "the"] + sign + [m.group(3)], 1, trail
        m = re.match(r"^(\d+(?:\.\d+)?)-([A-Za-zµμ]+)$", core)
        if m and m.group(2) in UNITS:
            return [m.group(1)] + UNITS[m.group(2)][0].split(" "), 1, trail
        # Roman numerals: "Elizabeth I ruled", "Act I", "section ii", a year "MCMXCIV"
        if core == "I" and prev[:1].isupper() and pl in REGNAL and (nl.endswith("ed") or nl in (
                "was", "had", "is", "of", "and", "became", "died", "who", "'s", "reigned", "ruled")):
            return ["the", "first"], 1, trail
        if core == "I" and pl in ROMAN_CUE and prev[:1].isupper():
            return ["one"], 1, trail
        if core.islower() and len(core) >= 2 and ROMAN.match(core.upper()) and pl in ROMAN_CUE:
            return [cardinal(roman_value(core.upper()))], 1, trail
        if core.startswith("M") and len(core) >= 4 and ROMAN.match(core):
            v = roman_value(core)
            if 1000 <= v <= 2099:
                return year_words(v), 1, trail
        if len(core) == 2 and core.isupper() and core.isalpha() and core.isascii() and not self.cased(core) \
                and not self.common(low) and not ROMAN.match(core) and not self.spelled(low) and \
                not (i and toks[i - 1].isupper() and toks[i - 1].isalpha() and len(toks[i - 1]) > 3):
            return self.spell(core), 1, trail                # "UA": the lexicon's reading is a word, not letters
        if re.match(r"^(?:[A-Za-z]{1,2}\.)+[A-Za-z]{1,2}$", core) and trail.startswith(".") and \
                low not in ("e.g", "i.e", "a.m", "p.m") and any(c.islower() for c in core):
            return self.spell(core.replace(".", "")), 1, trail[1:] if len(trail) > 1 else trail
        # acronyms that are also words: "the WHO", "the IT team"
        if core in ("WHO", "IT", "AM", "OR", "IS", "AS") and pl == "the":
            return self.spell(core), 1, trail
        # heteronyms said as an adjective
        if low == "minute" and (pl in ("is", "are", "was", "were", "very", "so", "quite", "extremely", "too",
                                       "seemed", "looked") or nl in (
                "details", "detail", "amounts", "amount", "traces", "trace", "particles", "quantities", "changes",
                "differences", "fraction", "portion", "particle")):
            return [core + PH + ADJ_FORMS["minute"]], 1, trail
        if low == "content" and nl in ("with", "to") and pl in (
                "seemed", "seem", "seems", "feel", "felt", "feels", "be", "been", "is", "was", "are", "were", "am",
                "remain", "remained", "quite", "very", "perfectly", "more", "less", "not", "looked", "looks"):
            return [core + PH + ADJ_FORMS["content"]], 1, trail
        if low == "fl" and trail.startswith(".") and re.match(r"^\d+(st|nd|rd|th)$", prev):
            return ["floor"], 1, trail[1:]
        return None

    def more2(self, core, trail, prev, prev2, nxt, nxt_raw, toks, i, pauses):
        """Third-round rules (the real-world batch): shorthand, weekday and date ranges, codes, zones."""
        low, pl, nl = core.lower(), prev.lower(), nxt.lower()
        is_num = lambda x: bool(re.match(r"^-?\d[\d,]*(\.\d+)?$", x))  # noqa: E731
        # chat and business shorthand
        if core in SHORTHAND_CASED and pl != "the":            # "the IMO" is an organisation
            return SHORTHAND_CASED[core].split(" "), 1, trail
        if low in SHORTHAND and not core.isupper() and pl != "the" and (low != "re" or trail.startswith(":")):
            return SHORTHAND[low].split(" "), 1, trail
        if low in ("w/", "w/o", "b/c"):
            return {"w/": ["with"], "w/o": ["without"], "b/c": ["because"]}[low], 1, trail
        if core in ("→", "->", "=>"):
            return ["to"], 1, trail
        if core == "@" and prev and nxt:
            return ["at"], 1, trail
        if core == "St" and not trail.startswith(".") and prev[:1].isupper() and prev.isalpha() and \
                (trail or not nxt or nxt[:1].islower()):
            return ["Street"], 1, trail
        if re.match(r"^[1-9]\d{2}[A-Z]?$", core) and pl.rstrip(".") in ("room", "rm", "suite", "ste", "gate", "apt",
                                                                        "apartment", "unit", "flight"):
            d, tail = core[:3], self.spell(core[3:])
            return [ONES[int(d[0])]] + (["hundred"] if d[1:] == "00" else ["oh", ONES[int(d[2])]] if d[1] == "0"
                                        else [d[1:]]) + tail, 1, trail
        m = re.match(r"^([A-Z]{2,4})(?:→|->)([A-Z]{2,4})$", core)
        if m:
            return self.spell(m.group(1)) + ["to"] + self.spell(m.group(2)), 1, trail
        # a lone dash between two days, dates or numbers: "Mon – Fri", "Dec 24 – Jan 2"
        if core in ("–", "-", "—") and prev and nxt:
            if (pl.rstrip(".") in DAY_ABBR or prev in DAY_ABBR.values()) and \
                    (nl.rstrip(".") in DAY_ABBR or nxt in DAY_ABBR.values()):
                return ["through"], 1, trail
            if (prev[:1].isdigit() or pl.rstrip(".") in MONTH_ABBR) and (nxt[:1].isdigit() or
                                                                          nl.rstrip(".") in MONTH_ABBR):
                return ["to"], 1, trail
        # weekdays written short without a full stop, before a date, a time or a range: "Tue 11/4", "Sat 10–2"
        if low in DAY_ABBR and core[0].isupper() and core.isalpha() and \
                (nxt[:1].isdigit() or nl in DAY_ABBR or nxt in ("–", "-") or (trail == "," and i + 1 < len(toks))):
            return [DAY_ABBR[low]], 1, trail
        m = re.match(r"^([A-Z][a-z]{2})[–-]([A-Z][a-z]{2})$", core)
        if m and m.group(1).lower() in DAY_ABBR and m.group(2).lower() in DAY_ABBR:
            return [DAY_ABBR[m.group(1).lower()], "through", DAY_ABBR[m.group(2).lower()]], 1, trail
        # a date after a weekday or "on": "Tue 11/4" -> November fourth
        m = re.match(r"^(\d{1,2})/(\d{1,2})$", core)
        if m and 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= 31 and \
                (prev in DAY_ABBR.values() or pl.rstrip(".,") in DAY_ABBR or pl in ("on", "by", "due", "until",
                                                                                     "till", "from", "before",
                                                                                     "after", "dated", "thru")):
            return [MONTHS[int(m.group(1)) - 1], ordinal(int(m.group(2)))], 1, trail
        # a month after an ordinal: "1st Feb" -> first of February
        if low.rstrip(".") in MONTH_ABBR and core[0].isupper() and re.match(r"^\d{1,2}(st|nd|rd|th)$", prev):
            return ["of", MONTHS[MONTH_ABBR[low.rstrip(".")] - 1]], 1, trail[1:] if trail.startswith(".") else trail
        # time zones after a time
        if core in ZONES and (self.TIME.match(prev) or re.match(r"^(?i:[ap]\.?m\.?)$", prev) or prev in ("AM", "PM")):
            return ZONES[core].split(" "), 1, trail
        # "8:40a", "11:25p"
        m = re.match(r"^(\d{1,2}):(\d{2})([ap])$", core)
        if m:
            return self.time(m.group(1), m.group(2), None, m.group(3)), 1, trail
        # hour ranges: "10–11:30", "9–5"
        m = re.match(r"^(\d{1,2})(?::(\d{2}))?[–-](\d{1,2})(?::(\d{2}))?$", core)
        if m and (m.group(2) or m.group(4)) and int(m.group(1)) <= 24 and int(m.group(3)) <= 24 and \
                not prev[:1].isupper():                          # "Torah 3:10-11" is chapter and verse
            a = self.time(m.group(1), m.group(2) or "00", None, None) or [m.group(1)]
            b = self.time(m.group(3), m.group(4) or "00", None, None) or [m.group(3)]
            return [w for w in a if w != "hundred"] + ["to"] + [w for w in b if w != "hundred"], 1, trail
        # durations and distances glued: "2h", "15m" (after hours), "400m"
        m = re.match(r"^(\d+(?:\.\d+)?)(h|hr|m|min|s)$", core)
        if m:
            n, u = m.group(1), m.group(2)
            if u in ("h", "hr"):
                return [n, "hour" if n == "1" else "hours"], 1, trail
            if u == "min" or u == "m" and re.match(r"^\d+(h|hr)$", prev):
                return [n, "minute" if n == "1" else "minutes"], 1, trail
            if u == "s" and re.match(r"^\d+(m|min)$", prev):
                return [n, "second" if n == "1" else "seconds"], 1, trail
            if u == "m" and (pl in ("the", "a", "ran", "run", "runs", "swam", "swim", "won", "in", "over", "under",
                                    "about", "climbed", "dove", "fell", "jumped") and nl not in ("for", "in", "dollars",
                                                                                                 "people", "users")
                             or nl in ("race", "dash", "sprint", "freestyle", "hurdles", "relay", "run", "swim",
                                       "high", "deep", "long", "tall", "wide", "away", "above", "below")):
                return [n, "meter" if n == "1" else "meters"], 1, trail
        # "$75+", "1,000+ users"
        m = re.match(r"^([$€£¥]?)(\d[\d,]*(?:\.\d+)?)\+$", core)
        if m:
            if m.group(1):
                return self.sub(m.group(1) + m.group(2), pauses) + ["or", "more"], 1, trail
            return ["more", "than", m.group(2)], 1, trail
        # a price after "a" or "an" is a modifier: "a $5 late fee"
        m = self.MONEY.match(core)
        if m and m.group(3) and not m.group(4) and not m.group(5) and pl in ("a", "an") and \
                nxt[:1].islower() and nl not in ("a", "an", "the", "and", "or", "for", "per", "each", "to"):
            return [m.group(3), CURRENCY[m.group(2)][0]], 1, trail
        # the last four of a card, a text short code
        if re.match(r"^\d{4}$", core) and (pl == "ending" or pl == "in" and prev2 == "ending"):
            return digit_words(core), 1, trail
        if re.match(r"^\d{5,6}$", core) and pl == "to" and any(self.split(t)[1].lower() == "text"
                                                             for t in toks[max(0, i - 4):i]):
            return digit_words(core), 1, trail
        # a postal code before a city
        if re.match(r"^\d{5}$", core) and nxt[:1].isupper() and i and toks[i - 1].endswith(","):
            return digit_words(core), 1, trail
        # codes and passwords: "abc123", "B12", "Win10"
        m = re.match(r"^(?i:win)(\d{1,2})$", core)
        if m:
            return ["Windows", m.group(1)], 1, trail
        m = re.match(r"^([a-z]{1,4})(\d{1,6})$", core)        # a code or password: "abc123"
        if m and m.group(1) not in ("x", "ext") and not self.known(low) and \
                (len(m.group(1)) <= 3 or not self.known(m.group(1))):
            d = m.group(2)
            return self.spell(m.group(1)) + ([d] if len(d) <= 2 else digit_words(d)), 1, trail
        # directions after a highway number or before a numbered street: "Hwy 101 N", "45 W 34th St."
        if core in ("N", "S", "E", "W") and is_num(prev) and (
                prev2 in ("hwy", "highway", "route", "rte", "interstate", "i", "us", "sr")
                or re.match(r"^\d+(st|nd|rd|th)$", nxt) or nxt[:1].isupper() and len(nxt) > 2):
            return [DIRECTIONS[low]], 1, trail
        if low in ("rm", "apt", "bldg", "fl") and core[0].isupper() and (nxt[:1].isdigit() or nxt.startswith("#")):
            word = {"rm": "Room", "apt": "Apartment", "bldg": "Building", "fl": "Floor"}[low]
            return [word], 1, trail[1:] if trail.startswith(".") else trail
        if low == "approx" and (nxt[:1].isdigit() or nxt[:1] in "$~"):
            return ["approximately"], 1, trail[1:] if trail.startswith(".") else trail
        # units after a fraction or a range: "1/2 tsp", "40–45 min"
        frac_word = pl in ("half", "quarter", "third", "eighth", "quarters", "thirds", "eighths")
        if core in UNITS and core not in ("m", "g", "L", "W", "V", "s") and (
                self.FRACTION.match(prev) or re.match(r"^\d+[–-]\d+$", prev) or frac_word):
            sing, plur = UNITS[core]
            one = self.FRACTION.match(prev) or pl in ("half", "quarter", "third", "eighth")
            return (sing if one else plur).split(" "), 1, trail
        # a single letter after a word that names classes of things: "Series A", "Plan B"
        if core == "A" and pl in LETTER_CUE and prev[:1].isupper():
            return [self.letter("A")], 1, trail
        # Roman numerals after a ruler's name ("Henry V tonight"), "Rocky IV"
        if core in ("V", "X") and pl in REGNAL and prev[:1].isupper():
            return ["the", ordinal(roman_value(core))], 1, trail
        if core in ("IV", "VI", "IX", "XI") and prev[:1].isupper() and prev.isalpha() and not prev.isupper():
            v = roman_value(core)
            return (["the", ordinal(v)] if pl in REGNAL else [cardinal(v)]), 1, trail
        # an imperative "Read" opens a sentence (leokani.py's respelling takes "before" as past tense)
        if core == "Read" and (i == 0 or toks[i - 1][-1:] in ".!?:;") and (nl in OBJECTS or nxt[:1].isupper()):
            return [core + PH + "ɹˈid"], 1, trail
        # accents the lexicon doesn't have: "Kīlauea", "Hawaiʻi", "Ó"
        plain = strip_okina(core)
        if plain != core and plain.isascii() and plain.isalpha() and not self.known(low) and \
                plain.lower() not in SAY_AS and \
                (self.known(plain.lower()) or len(plain) == 1):
            return [plain], 1, trail
        # three capitals the lexicon reads as a word but nobody would: "HOA"
        if len(core) == 3 and core.isupper() and core.isalpha() and core.isascii() and not self.cased(core) and \
                not self.common(low) and core not in ACRONYM_WORDS and not ROMAN.match(core) and \
                not self.spelled(low) and not (i and toks[i - 1].isupper() and len(toks[i - 1]) > 3):
            return self.spell(core), 1, trail
        # heteronyms
        if low == "lead" and pl in ("for", "of", "contains", "containing", "with", "no", "free", "test", "testing",
                                    "tested") and nl not in ("the", "a", "an", "us", "them", "you", "him", "her",
                                                             "me", "to", "our", "your", "their", "his", "my"):
            return [core + PH + "lˈɛd"], 1, trail
        if low == "does" and (pl in NUMBER_WORDS or prev.isdigit() or pl in ("the", "some", "many", "several",
                                                                              "two", "three", "few", "and")) \
                and nl not in ("not", "it", "he", "she", "this", "that", "anyone", "anybody", "everyone"):
            return [core + PH + "dˈOz"], 1, trail
        if low == "row" and nl in ("over", "about", "with", "between") and pl in ("a", "the", "big", "huge",
                                                                                   "blazing", "public", "family",
                                                                                   "another", "furious"):
            return [core + PH + "ɹˈW"], 1, trail
        if low == "minute" and pl in ("a", "the") and nl in MINUTE_NOUNS:
            return [core + PH + ADJ_FORMS["minute"]], 1, trail
        return None

    # ---- v1.2: letters, codes, ranges and units (the v1.2 blind batches)
    def letter_plural(self, c: str, possessive: str = "") -> str:
        """'Os' in "CEOs", 'C's' in "AGC's": a letter name said with a plural or possessive ending."""
        ph = self.letters.get(c.lower(), "")
        return f"{c.upper()}{possessive or 's'}{PH}{ph}{'ᵻz' if c.lower() in LETTER_PLURAL_ES else 's' if c.lower() in LETTER_PLURAL_S else 'z'}"

    def initialism(self, w: str) -> bool:
        """An all-caps run said letter by letter: the lexicon spells it, or it doesn't know it and English can't
        say it as a word."""
        if w in ACRONYM_WORDS or w in SAY_AS_CASED or ROMAN.match(w) or not (w.isascii() and w.isalpha()):
            return False
        if self.cased(w):
            return False
        if self.known(w.lower()):
            return self.spelled(w.lower()) and len(self.reading(w.lower())) > 0
        return not pronounceable(w)

    def single(self, t: str) -> bool:
        c = self.split(t)[1]
        return len(c) == 1 and c.isalpha() and c.isupper() and c.isascii()

    def shouted(self, toks: list[str], i: int) -> bool:
        """The words around token i are written in capitals as ordinary words ("PLEASE READ THE MANUAL")."""
        n = 0
        for j in (i - 2, i - 1, i + 1, i + 2):
            if 0 <= j < len(toks):
                c = self.split(toks[j])[1]
                if len(c) >= 3 and c.isupper() and c.replace("'", "").replace("’", "").isalpha() and \
                        self.known(c.lower()) and not self.initialism(c):
                    n += 1
        return n >= 2

    def letters_first(self, core, trail, prev, prev2, nxt, nxt_raw, toks, i, pauses):
        """v1.2 letter rules, ahead of every other rule: spaced, dotted and hyphenated letters, initialisms with
        endings, shouted words."""
        low, pl, nl = core.lower(), prev.lower(), nxt.lower()
        # spaced single letters: "A G C" ("A-G-C" and "c-a-t" stay one token, spelled as v1.1 does); a lone "A" or "I" before a
        # word stays the article or the pronoun
        if core in ("A", "I"):
            after_letter = i > 0 and self.single(toks[i - 1]) and self.split(toks[i - 1])[1] not in ("A", "I") \
                and not toks[i - 1][-1:] in ".!?;:"
            before_letter = not trail and i + 1 < len(toks) and self.single(nxt_raw)
            if after_letter or before_letter or (core == "A" and (pl in ("letter", "letters", "an") or (
                    nl in ("and", "or") and not trail) or (trail[:1] in ",;" and self.single(nxt_raw)))) or (
                    pl in ("and", "or") and i > 1 and self.single(toks[i - 2])):
                return [self.letter(core)], 1, trail
        # plural and possessive initialisms: "CEOs", "PDFs", "AGC's"
        m = re.match(r"^([A-Z]{2,6})(s|'s|’s)$", core)
        if m and m.group(1) not in SHORTHAND_CASED and self.initialism(m.group(1)) and core not in SHORTHAND_CASED \
                and core != "IDs":                                           # "IDs" keeps v1.1's reading
            st = m.group(1)
            return self.spell_word(st, m.group(2)), 1, trail
        # dotted capitals: "A.G.C.", "N.Y.C.", "A.I." (the full stop ends a sentence only before a capital or at the end)
        if re.match(r"^(?:[A-Z]\.){1,}[A-Z]$", core) and trail.startswith(".") and len(core) >= 3:
            keep = trail if i + 1 >= len(toks) or nxt[:1].isupper() and nxt != "I" else trail[1:]
            if core.replace(".", "") in ACRONYM_WORDS:                       # "N.A.T.O." is still Nato
                return [core.replace(".", "")], 1, keep
            return self.spell_word(core.replace(".", "")), 1, keep
        # a middle initial: "George W. Bush", "Ulysses S. Grant" (not a direction)
        initial = lambda t: bool(re.match(r"^[A-Z]\.$", t))  # noqa: E731
        if len(core) == 1 and core.isupper() and trail == "." and nxt[:1].isupper() and nl not in SENTENCE_START \
                and (initial(nxt_raw) or i and initial(toks[i - 1]) and nxt.isalpha() or
                     prev[:1].isupper() and prev.isalpha() and not prev.isupper() and len(nxt) > 1 and nxt.isalpha()
                     and toks[i - 1][-1:] not in ".!?:;,") and \
                not any(self.split(t)[1].lower().rstrip(".") in STREET_WORDS for t in toks[i + 1:i + 4]):
            return [self.letter(core)], 1, trail[1:]
        # a letter before a word: "p-value", "t-test", "x-axis"; a word before a letter: "Type-C", "Plan-B"
        m = re.match(r"^([a-zA-Z])-(value|values|test|tests|axis|score|scores|statistic|coordinate|intercept)$", core)
        if m:
            return [self.letter(m.group(1)), m.group(2)], 1, trail
        m = re.match(r"^([A-Za-z]{2,})-([A-Z])$", core)
        if m and m.group(1).isalpha():
            return [m.group(1), self.letter(m.group(2))], 1, trail
        # a letter and a model number: "F-150", "B-52", "F-16"
        m = re.match(r"^([A-Z]{1,2})-(\d{2,3})$", core)
        if m and core[:2] != "I-":
            d = m.group(2)
            num = cardinal(int(d)).split(" ") if len(d) == 2 or d[1] == "0" and d[2] == "0" else \
                [ONES[int(d[0])]] + (["oh", ONES[int(d[2])]] if d[1] == "0" else cardinal(int(d[1:])).split(" "))
            return self.spell(m.group(1)) + num, 1, trail
        # mixed-case initialisms: "DoD", "DoE", "MoU"
        if re.match(r"^[A-Z]o[A-Z]s?$", core) and core not in SAY_AS_CASED:
            return self.spell_word(core[:3], core[3:]), 1, trail
        # a resolution: "1080p", "720p", "4K" stays
        m = re.match(r"^(\d{3,4})([pi])$", core)
        if m:
            d = m.group(1)
            return (pair_words(int(d)) if len(d) == 4 else [ONES[int(d[0])]] + cardinal(int(d[1:])).split(" ")) + \
                [self.letter(m.group(2))], 1, trail
        # a possessive of a capitalised word: "NATO's"
        m = re.match(r"^([A-Z]{4,})(['’]s)$", core)                        # "WHO's" stays v1.1's
        if m and not self.initialism(m.group(1)) and self.reading(m.group(1).lower()):
            ph = self.reading(m.group(1).lower())[0]
            end = "ᵻz" if ph[-1:] in SIBILANT_END else "s" if ph[-1:] in VOICELESS_END else "z"
            return [core + PH + ph + end], 1, trail
        # a common word shouted in capitals keeps its word reading ("I CAN'T BELIEVE IT"), not its letters
        if len(core) >= 2 and core.isupper() and core.replace("'", "").replace("’", "").isalpha() and \
                self.known(low) and core not in ACRONYM_WORDS and core not in SAY_AS_CASED and \
                core not in SHORTHAND_CASED and core not in ZONES and not ROMAN.match(core) and \
                (self.common(low) or not self.cased(core)) and self.shouted(toks, i) and \
                any(not self.spelled_form(f, low) for f in self.reading(low)):
            return [low if i and toks[i - 1][-1:] not in ".!?" else low.capitalize()], 1, trail
        return None

    def spelled_form(self, f: str, w: str) -> bool:
        bare = lambda x: x.replace(PRIMARY, "").replace(SECONDARY, "").replace(" ", "")  # noqa: E731
        return bare(f) == "".join(bare(self.letters.get(c, "?")) for c in w)

    def more3(self, core, trail, prev, prev2, nxt, nxt_raw, toks, i, pauses):
        low, pl, nl = core.lower(), prev.lower(), nxt.lower()
        is_num = lambda x: bool(re.match(r"^-?\d[\d,]*(\.\d+)?$", x))  # noqa: E731
        sing_unit = lambda n, u: (UNITS[u][0] if n in ("1", "-1") else UNITS[u][1]).split(" ")  # noqa: E731
        # respelled capitals: "IEEE", "WWII", "PhD"
        if core in CASED_SAY:
            return self.sub(CASED_SAY[core], pauses), 1, trail
        if core == "ID":                                                     # "your ID": not the Freudian id ("IDs"
            return [core + PH + "ˌIdˈi"], 1, trail                           # keeps v1.1's reading)
        # year ranges: "1990–95", "2019-2020 season"
        m = re.match(r"^(1[1-9]\d\d|20\d\d)[–-](\d\d|1[1-9]\d\d|20\d\d)$", core)
        if m and not core.endswith("00") or m and re.match(r"^(1[1-9]\d\d|20\d\d)[–-](\d\d|\d{4})$", core) and \
                int(m.group(1)) % 100:
            a, b = int(m.group(1)), m.group(2)
            bw = year_words(int(b)) if len(b) == 4 else (["oh", ONES[int(b[1])]] if b[0] == "0" else
                                                         cardinal(int(b)).split(" "))
            if len(b) == 4 and int(b) <= a or len(b) == 2 and int(b) <= a % 100:
                pass                                                          # not a range: a code
            else:
                joint = [] if nl in ("season", "seasons", "school", "academic", "fiscal", "tax", "budget",
                                     "financial") else ["to"]
                return year_words(a) + joint + bw, 1, trail
        # a range in percent: "20–30%"
        m = re.match(r"^(\d[\d,]*(?:\.\d+)?)[–-](\d[\d,]*(?:\.\d+)?)%$", core)
        if m:
            return [m.group(1), "to", m.group(2), "percent"], 1, trail
        # day ranges after a month: "Jan 3–7", "May 12-19"
        m = re.match(r"^(\d{1,2})[–-](\d{1,2})$", core)
        if m and (prev in MONTHS or pl.rstrip(".") in MONTH_ABBR and prev[:1].isupper()) and \
                1 <= int(m.group(1)) < int(m.group(2)) <= 31:
            return [ordinal(int(m.group(1))), "to", ordinal(int(m.group(2)))], 1, trail
        # fraction ranges: "1/2-1 cup", "1–1/2 tsp"
        m = re.match(r"^(\d{1,2}(?:/\d{1,2})?)[–-](\d{1,2}(?:/\d{1,2})?)$", core)
        if m and "/" in core:
            out = []
            for k, part in enumerate(m.groups()):
                if "/" in part:
                    fr = self.fraction(*(int(x) for x in part.split("/")))
                    if not fr:
                        out = None
                        break
                    out += (["to"] if k else []) + fr
                else:
                    out += (["to"] if k else []) + [part]
            if out:
                return out, 1, trail
        # aircraft: "Boeing 737-800", "Airbus A320"
        m = re.match(r"^([1-9])(\d\d)(?:-(\d{1,3}))?$", core)
        if m and pl in ("boeing", "airbus", "embraer", "bombardier", "douglas", "md", "dc"):
            return [ONES[int(m.group(1))]] + cardinal(int(m.group(2))).split(" ") + \
                (cardinal(int(m.group(3))).split(" ") if m.group(3) else []), 1, trail
        # years with an era: "A.D. 1250", "500 BC"
        if re.match(r"^\d{3,4}$", core) and (prev.rstrip(".") in ("A.D", "AD", "B.C", "BC", "CE", "BCE", "B.C.E") or
                                            nxt.rstrip(".") in ("A.D", "AD", "B.C", "BC", "CE", "BCE", "B.C.E")) \
                and not core.endswith("00"):
            return year_words(int(core)), 1, trail
        # a month before a day range: "Jan 3–7"
        if low.rstrip(".") in MONTH_ABBR and core[0].isupper() and core.isalpha() and \
                re.match(r"^\d{1,2}[–-]\d{1,2}$", nxt):
            return [MONTHS[MONTH_ABBR[low.rstrip(".")] - 1]], 1, trail[1:] if trail.startswith(".") else trail
        # a port: "port 443", "port 8080"
        if re.match(r"^\d{2,5}$", core) and pl in ("port", "ports") and not prev2 in ("the", "a"):
            return (pair_words(int(core)) if len(core) == 4 and core[1:] != "000" and int(core) < 2100
                    else [core[:2], core[2:]] if len(core) == 4 and core[2] != "0" and core[1:] != "000"
                    else [core[0], core[1:]] if len(core) == 3 and core[1] != "0"
                    else [core]), 1, trail
        # a weekday after a dash: "Tue–Thu", "Mon - Fri"
        if low in DAY_ABBR and core[0].isupper() and core.isalpha() and (prev in ("–", "-", "—", "through", "to") or
                                                                          pl in ("thru", "until", "till")) and \
                not (prev in ("through", "to") and nxt[:1].isupper() and nxt.isalpha() and nl not in DAY_ABBR and nxt not in DAY_ABBR.values() and
                     nl not in MONTH_ABBR):                                  # "I talked to Thu Crosson"
            return [DAY_ABBR[low]], 1, trail[1:] if trail.startswith(".") else trail
        # phone numbers: "312 555 0199", "+33 1 42 68 53 00", "ext 12", "988", ZIP+4
        if re.match(r"^\d{3}$", core) and re.match(r"^\d{3}$", nxt) and i + 2 < len(toks) and \
                not toks[i].startswith("(") and not (i and re.match(r"^\+\d{1,3}$", toks[i - 1])) and \
                re.match(r"^\d{4}$", self.split(toks[i + 2])[1]) and not self.split(nxt_raw)[2]:
            z = self.split(toks[i + 2])
            return self.phone([core, nxt, z[1]], pauses), 3, z[2]
        if low in ("ext", "extension", "x") and not trail and re.match(r"^\d{1,5}$", nxt) and (
                low != "x" or re.search(r"\d", prev)) and i:
            z = self.split(nxt_raw)
            return ["extension"] + (digit_words(z[1]) if len(z[1]) > 2 else [z[1]]), 2, z[2]
        if core == "988" and (pl in ("call", "text", "dial", "or") or not nxt):
            return digit_words(core), 1, trail
        if re.match(r"^\d{5}-\d{4}$", core):
            return digit_words(core.replace("-", "")), 1, trail
        if re.match(r"^\d{4}$", core) and pl == "in" and prev2 in ("ends", "ending") and (
                not 1100 <= int(core) <= 2099 or any(self.split(t)[1].lower() in CODE_CUE | {"card", "phone"}
                                                     for t in toks[max(0, i - 6):i])):
            return digit_words(core), 1, trail
        # codes after a cue word: "tracking number 9400111899", "code 482913", "Invoice 2024-0915", "SN 555123"
        cue = [self.split(t)[1].lower().rstrip(":#") for t in toks[max(0, i - 3):i]]
        if re.match(r"^#?\d{4,}([-]\d{2,})*$", core) and not is_num(core.replace("-", "x")) and "-" in core or \
                re.match(r"^\d{5,}$", core):
            if cue[-3:] == ["the", "code", "is"]:                            # "The code is 351576." reads the number
                pass
            elif any(c in CODE_CUE for c in cue[-2:]) or cue[-1:] == ["is"] and any(c in CODE_CUE for c in cue):
                return digit_words(re.sub(r"\D", "", core)), 1, trail
        if re.match(r"^\d{4}-\d{3,}$", core) and any(c in CODE_CUE for c in cue[-2:]):
            return digit_words(core.replace("-", "")), 1, trail
        # units: "100 m²", "500 MB/s", "10 sq ft", "2 in long", "180 °C", "250 g of flour"
        m = re.match(r"^(\d[\d,]*(?:\.\d+)?)?(km|m|cm|mm|ft|in|mi|yd)([²³])$", core)
        if m and (m.group(1) or is_num(prev)):
            n = m.group(1) or prev
            u = {"in": "inch"}.get(m.group(2), m.group(2))
            name = UNITS[m.group(2)] if m.group(2) in UNITS else ("inch", "inches")
            words = ("square " if m.group(3) == "²" else "cubic ") + (name[0] if n in ("1", "-1") else name[1])
            return ([n] if m.group(1) else []) + words.split(" "), 1, trail
        m = re.match(r"^(\d[\d,]*(?:\.\d+)?)?([KMGT]B|[kMG]b|km|m|ft|mi)/(s|sec|h|hr|min)$", core)
        if m and (m.group(1) or is_num(prev)):
            n = m.group(1) or prev
            u = m.group(2)
            name = UNITS.get(u) or {"Mb": ("megabit", "megabits"), "Gb": ("gigabit", "gigabits"),
                                    "kb": ("kilobit", "kilobits")}[u]
            per = {"s": "second", "sec": "second", "h": "hour", "hr": "hour", "min": "minute"}[m.group(3)]
            return ([n] if m.group(1) else []) + (name[0] if n in ("1", "-1") else name[1]).split(" ") + \
                ["per", per], 1, trail
        if low in ("sq", "sq.", "cu") and is_num(prev) and (nxt in UNITS or nl in ("in", "ft")):
            z = self.split(nxt_raw)
            u = z[1] if z[1] in UNITS else z[1].lower()
            name = UNITS[u] if u in UNITS else ("inch", "inches")
            return ["square" if low.startswith("sq") else "cubic"] + \
                (name[0] if prev in ("1", "-1") else name[1]).split(" "), 2, z[2].lstrip(".") if z[2] != "." else z[2]
        if core == "in" and is_num(prev) and not trail and nl in ("long", "wide", "tall", "deep", "thick", "high",
                                                                  "across", "diameter", "square"):
            return ["inch" if prev == "1" else "inches"], 1, trail
        if core in ("°C", "°F", "°") and is_num(prev):
            return (["degree"] if prev in ("1", "-1") else ["degrees"]) + \
                ({"°C": ["Celsius"], "°F": ["Fahrenheit"]}.get(core, [])), 1, trail
        if core == "g" and is_num(prev) and (nl in ("of", "") or trail):
            return sing_unit(prev, "g"), 1, trail
        # Roman numerals: a list item "i." at the start of a line, "Grand Theft Auto V"
        if i == 0 and trail == "." and ROMAN.match(core.upper()) and (core.islower() or len(core) > 1 and core.isupper()) and \
                nxt[:1].isupper():
            return [cardinal(roman_value(core.upper())).capitalize()], 1, trail
        if core == "V" and prev[:1].isupper() and prev.isalpha() and not prev.isupper() and pl not in REGNAL and \
                pl not in LETTER_CUE and i > 1 and toks[i - 1][-1:] not in ".!?:;" and (not nxt or nxt[:1].islower()):
            return ["five"], 1, trail
        # web: "https" said as letters, "@bakes.by.bella", "@NYTimes"
        if low in ("http", "https") and core.islower():
            return self.spell(low), 1, trail
        if re.match(r"^@[A-Za-z0-9_]+(\.[A-Za-z0-9_]+)+$", core):
            return ["at"] + self.say_parts(core[1:]), 1, trail
        if re.match(r"^@[A-Za-z0-9_]+$", core) and re.search(r"[a-z]", core) and re.search(r"[A-Z]{2}[a-z]", core):
            words = ["at"]
            for part in re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+|\d+|_", core[1:]):
                words += ["underscore"] if part == "_" else self.say_run(part) if not part.isupper() \
                    else self.spell(part) if self.initialism(part) or len(part) <= 3 else [part]
            return words, 1, trail
        return None

    def capitals(self, core, trail, prev, nxt, toks, i):
        """Last: an all-caps word the lexicon doesn't have is spelled unless English could say it as a word."""
        if len(core) >= 2 and core.isupper() and core.isalpha() and core.isascii() and not self.known(core.lower()) \
                and not self.cased(core) and self.initialism(core):
            return self.spell_word(core), 1, trail
        return None

    def ip(self, host: str) -> list[str]:
        """192.168.1.1 -> one ninety-two dot one sixty-eight dot one dot one."""
        words = []
        for k, x in enumerate(host.split(".")):
            n = int(x)
            w = cardinal(n).split(" ") if n < 100 or n % 100 == 0 else \
                [ONES[n // 100]] + (["oh", ONES[n % 10]] if n % 100 < 10 else [cardinal(n % 100)])
            words += (["dot"] if k else []) + w
        return words

    def basic(self, core, trail, prev, prev2, prev_end, nxt, nxt_raw, toks, i, pauses):
        """First-round rules (the edge corpus)."""
        low = core.lower()
        dot = trail.startswith(".")
        # sentence end after an abbreviation: keep the full stop only at the end of the line or before a capital
        keep_dot = trail if (i + 1 >= len(toks) or nxt[:1].isupper()) else trail[1:]
        nxt_cap = nxt[:1].isupper()
        prev_cap = prev[:1].isupper() and prev.isalpha() or bool(re.match(r"^\d+(st|nd|rd|th)?$", prev))
        nxt_num = nxt[:1].isdigit()
        prev_num = bool(re.match(r"^-?\d[\d,]*(\.\d+)?$", prev))

        # -- symbols and digits
        m = self.EMAIL.match(core)
        if m:
            return self.say_parts(m.group(1)) + ["at"] + self.domain(m.group(2)), 1, trail
        if core.startswith("@") and re.match(r"^@[A-Za-z0-9_]+$", core):
            return ["at"] + self.say_parts(core[1:]), 1, trail
        if core.startswith("#") and len(core) > 1:
            if core[1:].isdigit():
                return ["number"] + (digit_words(core[1:]) if len(core) > 4 else [core[1:]]), 1, trail
            if re.match(r"^#[A-Za-z]\w*$", core):
                parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?![a-z])|\d+", core[1:])
                return ["hashtag"] + [p.lower() if self.known(p.lower()) else p for p in parts], 1, trail
        if re.match(r"^[A-G]#$", core):
            return [core[0], "sharp"], 1, trail
        m = self.URL.match(core)
        if m and (m.group(1) or m.group(2).rsplit(".", 1)[1].lower() in TLDS) and \
                re.search(r"[A-Za-z]{2}", m.group(2).split(".")[0]) and (m.group(1) or not dot or low.count(".") >= 1):
            host = m.group(2)
            if not m.group(1) and (host.rsplit(".", 1)[1] not in TLDS):
                return None
            if low in WORD_ABBR or (low + ".") in ("e.g.", "i.e."):
                return None
            words = []
            if host.lower().startswith("www."):
                words += self.spell("www") + ["dot"]
                host = host[4:]
            words += self.domain(host)
            for seg in (m.group(3) or "").split("/")[1:]:
                words.append("slash")
                if re.match(r"^[a-z]{2}[-_][a-z]{2}$", seg, re.I):
                    words += self.spell(seg[:2]) + [SEP_WORDS[seg[2]]] + self.spell(seg[3:])
                elif re.match(r"^[1-9]\d{0,3}$", seg):
                    words.append(seg)
                elif seg:
                    words += self.say_parts(seg)
            return words, 1, trail
        m = self.MONEY.match(core)
        if m and (m.group(3) or m.group(4)):
            nscale = nxt.lower() if nxt.lower() in SCALE_WORDS and not m.group(5) else None
            words = self.money(m.group(1), m.group(2), m.group(3), m.group(4), m.group(5), nscale)
            if nscale:
                return words, 2, self.split(nxt_raw)[2]
            return words, 1, trail
        m = self.CENTS.match(core)
        if m:
            return [m.group(1), "cent" if m.group(1) == "1" else "cents"], 1, trail
        m = self.DEGREES.match(core)
        if m and (m.group(2) or core.endswith("°")):
            n = m.group(1)
            words = (["minus", n[1:]] if n.startswith("-") else [n]) + ["degree" if n in ("1", "-1") else "degrees"]
            return words + ({"C": ["Celsius"], "F": ["Fahrenheit"]}.get(m.group(2), [])), 1, trail
        m = self.TOLLWORD.match(core)
        if m:
            return self.phone(["1", m.group(1), m.group(2)], pauses), 1, trail
        m = self.PHONE.match(core)
        if m:
            g = [x for x in m.groups() if x]
            return self.phone([x.lstrip("+") for x in g], pauses, plus=g[0].startswith("+")), 1, trail
        if re.match(r"^\(\d{3}\)$", toks[i]) or (re.match(r"^\d{3}$", core) and toks[i].startswith("(")):
            m2 = re.match(r"^(\d{3})-(\d{4})$", nxt)
            if m2:
                return self.phone([core, m2.group(1), m2.group(2)], pauses), 2, self.split(nxt_raw)[2]
        if re.match(r"^\+\d{1,3}$", core):
            groups, j = [core[1:]], i + 1
            while j < len(toks) and re.match(r"^\d{1,4}(-\d{1,4})*$", self.split(toks[j])[1]):
                groups += self.split(toks[j])[1].split("-")
                j += 1
                if self.split(toks[j - 1])[2]:
                    break
            if len(groups) >= 3:
                return self.phone(groups, pauses, plus=True), j - i, self.split(toks[j - 1])[2]
        m = self.PHONE7.match(core)
        if m and not prev_num:
            return self.phone([m.group(1), m.group(2)], pauses), 1, trail
        if re.match(r"^[2-9]11$", core) and (core == "911" or prev.lower() in ("dial", "call", "called", "calling")):
            return digit_words(core), 1, trail
        if self.IPV4.match(core) and all(int(x) < 256 for x in core.split(".")):
            return self.ip(core), 1, trail
        m = self.VERSION.match(core)
        if m and (m.group(2).count(".") >= 2 or m.group(1)):
            words = ["version"] if m.group(1) and prev.lower() not in ("version", "release", "v") else []
            for k, x in enumerate(m.group(2).split(".")):
                words += (["point"] if k else []) + ([x] if not (len(x) > 1 and x.startswith("0")) else digit_words(x))
            if m.group(3):
                words += [w for w in re.findall(r"[A-Za-z]+|\d+", m.group(3))]
            return words, 1, trail
        m = self.LEADING_POINT.match(core)
        if m:
            return ["point"] + digit_words(m.group(1)), 1, trail
        m = self.DECADE.match(core)
        if m and m.group(1).endswith("0") and (len(m.group(1)) == 2 or 1000 <= int(m.group(1)) <= 2090):
            return plural_number(int(m.group(1))).split(" "), 1, trail
        m = self.DATE_ISO.match(core)
        if m and 1 <= int(m.group(2)) <= 12 and 1 <= int(m.group(3)) <= 31:
            sep = "," if pauses else ""
            return [MONTHS[int(m.group(2)) - 1], ordinal(int(m.group(3))) + sep] + year_words(int(m.group(1))), 1, trail
        m = self.DATE_MDY.match(core)
        if m and 1 <= int(m.group(1)) <= 12 and 1 <= int(m.group(2)) <= 31:
            y = m.group(3) if len(m.group(3)) == 4 else ("20" if int(m.group(3)) < 50 else "19") + m.group(3)
            sep = "," if pauses else ""
            return [MONTHS[int(m.group(1)) - 1], ordinal(int(m.group(2))) + sep] + year_words(int(y)), 1, trail
        m = self.FRACTION.match(core)
        if m:
            n, d = int(m.group(1)), int(m.group(2))
            fr = self.fraction(n, d)
            unit_next = nxt.lower() in ("of", "inch", "inches", "cup", "cups", "mile", "miles", "teaspoon",
                                        "teaspoons", "tablespoon", "tablespoons", "pound", "pounds", "ounce",
                                        "ounces", "hour", "hours", "an", "a", "in", "tsp", "tbsp", "lb", "oz")
            if fr and (d in (2, 3, 4, 8) or unit_next or d in (16, 32, 64) and n % 2):
                return fr, 1, trail
            if 1 <= n <= 12 and 13 <= d <= 31:
                return [MONTHS[n - 1], ordinal(d)], 1, trail
            if (n, d) in ((24, 7), (9, 11), (7, 11), (50, 50), (24, 365)):
                return [str(n), str(d)], 1, trail
            return None
        if re.match(r"^\d+$", core) and self.FRACTION.match(nxt):
            n, d = (int(x) for x in nxt.split("/"))
            fr = self.fraction(n, d)
            if fr and int(core) < 1000:
                tail = ["a", fr[1]] if n == 1 else fr
                return [cardinal(int(core)), "and"] + tail, 2, self.split(nxt_raw)[2]
        m = self.TIME.match(core)
        if m and (m.group(3) or m.group(4) or m.group(2).startswith("0")):
            words = self.time(m.group(1), m.group(2), m.group(3), m.group(4))
            if words:
                return words, 1, trail
        m = self.TIME_AMPM.match(core)
        if m and int(m.group(1)) <= 12:
            return [m.group(1), self.letter(m.group(2)), "M"], 1, trail
        if core in ("am", "pm") and (prev_num or self.TIME.match(prev)):
            return [self.letter(core[0]), "M"], 1, trail
        m = self.RATIO.match(core)
        if m and not prev[:1].isupper() and not prev_num:
            return [m.group(1), "to", m.group(2)], 1, trail
        if re.match(r"^\d{1,2}:\d{2}[-–]\d{1,2}:\d{2}$", core):
            a, b = re.split(r"[-–]", core)
            wa = self.time(*a.split(":"), None, None) or [a]
            wb = self.time(*b.split(":"), None, None) or [b]
            return wa + ["to"] + wb, 1, trail
        m = self.RANGE.match(core)
        if m:
            a, b = m.group(1), m.group(2)
            if a == b:
                return [a, b], 1, trail
            return [a, "to", b], 1, trail
        m = self.TIMES_X.match(core)
        if m:
            return self.pairs(m.group(1)) + ["by"] + self.pairs(m.group(2)), 1, trail
        m = self.MULT.match(core)
        if m:
            return [m.group(1), "times"], 1, trail
        m = UNIT_GLUED.match(core)
        if m:
            sing, plur = UNITS[m.group(2)]
            return [m.group(1)] + (sing if m.group(1) == "1" else plur).split(" "), 1, trail
        if self.DIGITS.match(core):
            return digit_words(core), 1, trail
        if core in ("~", "≈") and nxt_num:
            return ["about"], 1, trail
        if core.startswith("~") and re.match(r"^~\d", core):
            return ["about", core[1:]], 1, trail
        if core in (">", "<", "*", "=", "+", "&", "±", ">=", "<=") and (prev_num or nxt_num or core == "&"):
            say = {">": ["is", "greater", "than"], "<": ["is", "less", "than"], "*": ["times"], "=": ["equals"],
                   "+": ["plus"], "&": ["and"], "±": ["plus", "or", "minus"], ">=": ["is", "at", "least"],
                   "<=": ["is", "at", "most"]}[core]
            if core in (">", "<") and prev.lower() in ("is", "are", "was", "were"):
                say = say[1:]
            return say, 1, trail
        if re.match(r"^[A-Z]{1,3}&[A-Z]{1,3}$", core):
            a, b = core.split("&")
            return self.spell(a) + ["and"] + self.spell(b), 1, trail
        if re.match(r"^[A-Za-z]+&[A-Za-z]+$", core):
            a, b = core.split("&")
            return [a, "and", b], 1, trail
        if re.search(r"[A-Za-z](—|--|–)[A-Za-z]", core):
            return [p for p in re.split(r"—|--|–", core) if p], 1, trail
        if re.match(r"^(?i:rock)['’]n['’](?i:roll)$", core):
            return [core.split("'")[0].split("’")[0], "and", "roll"], 1, trail

        # -- numbers followed by a unit
        if prev_num and core in UNITS and not (core in ("in", "m", "g") and not dot and core != "m"):
            if core == "in":
                return None
            sing, plur = UNITS[core]
            return (sing if prev in ("1", "-1") else plur).split(" "), 1, trail
        if prev_num and low == "in" and dot:
            return ["inch" if prev == "1" else "inches"], 1, keep_dot[1:] if keep_dot != trail else trail
        if prev_num and low in ("ft", "lbs", "lb", "oz", "hrs", "hr", "mins", "min", "secs", "sec", "yrs", "yr",
                                "tsp", "tbsp", "mi", "yds", "yd", "gal", "qt") and dot:
            w = WORD_ABBR[low]
            if prev not in ("1", "-1"):
                w = {"foot": "feet", "inch": "inches", "pound": "pounds", "ounce": "ounces", "hour": "hours",
                     "minute": "minutes", "second": "seconds", "year": "years", "teaspoon": "teaspoons",
                     "tablespoon": "tablespoons", "mile": "miles", "yard": "yards", "gallon": "gallons",
                     "quart": "quarts"}.get(w, w)
            return [w], 1, trail[1:] if not (i + 1 >= len(toks) or nxt_cap) else trail

        # -- abbreviations with a full stop
        if dot or low == "e.g":
            key = low
            if key == "e.g":
                return WORD_ABBR[key].split(" "), 1, trail[1:] if dot else trail
            if key == "no" and core in ("No", "no") and (nxt_num or nxt.startswith("#")):
                return ["number"], 1, trail[1:]
            if key in ("st", "dr") and core[0].isupper():
                # "Pine St. near", "Mulberry Dr." -> a street; "St. James", "Dr. Smith" stay (read right)
                if (prev_cap or prev_num) and not prev_end and not (nxt_cap and i + 1 < len(toks) and
                                                                    trail == "."):
                    return [STREET_ABBR[key]], 1, keep_dot if len(trail) == 1 else trail[1:]
                if key == "st" and nxt_cap and trail == ".":
                    return ["Saint"], 1, ""
                return None
            if key in ("jr", "sr") and core[0].isupper() and prev_cap:
                return [STREET_ABBR[key]], 1, keep_dot
            if key in TITLE_ABBR and core[0].isupper() and (nxt_cap or nxt_num):
                if key == "ft" and not nxt_cap:
                    return None
                return [TITLE_ABBR[key]], 1, trail[1:]
            if key in STREET_ABBR and core[0].isupper() and key not in ("st", "dr", "jr", "sr") and \
                    (prev_cap or prev_num):
                return [STREET_ABBR[key]], 1, keep_dot
            if key in MONTH_ABBR and core[0].isupper() and (nxt_num or prev_num):
                return [MONTHS[MONTH_ABBR[key] - 1]], 1, keep_dot
            if key in DAY_ABBR and core[0].isupper():
                return [DAY_ABBR[key]], 1, keep_dot
            if key in ("vs", "approx", "apt", "dept", "est", "fig", "vol", "ch", "pp", "ca", "cf", "corp", "govt",
                       "intl", "misc") and (key != "ch" or nxt_num) and (key != "est" or nxt_num) \
                    and (key not in ("fig", "vol", "pp", "apt") or nxt_num or nxt[:1].isupper()):
                return WORD_ABBR[key].split(" "), 1, trail[1:] if not (i + 1 >= len(toks) or nxt_cap) else trail
        if low in MONTH_ABBR and core[0].isupper() and core.isalpha() and nxt_num and \
                re.match(r"^\d{1,2}(st|nd|rd|th)?$", nxt) and low not in ("mar", "jun") or \
                (low in ("mar", "jun") and core[0].isupper() and re.match(r"^\d{1,2}(st|nd|rd|th)?$", nxt)):
            return [MONTHS[MONTH_ABBR[low] - 1]], 1, trail
        if low == "vs":
            return ["versus"], 1, trail

        # -- Roman numerals
        if ROMAN.match(core) and core.isupper():
            v = roman_value(core)
            pl = prev.lower()
            if v and pl in REGNAL and prev[:1].isupper() and (len(core) > 1 or trail or not nxt or nxt.lower() == "of"):
                return ["the", ordinal(v)], 1, trail
            if v and pl in ROMAN_CUE and prev[:1].isupper() and (len(core) > 1 or core in ("V", "X")) or \
                    v and pl in ROMAN_CUE and core == "I" and (trail or not nxt):
                return [cardinal(v)], 1, trail
            if v and len(core) > 1 and core not in ROMAN_AMBIGUOUS and prev[:1].isupper() and prev.isalpha() \
                    and not prev.isupper():
                return [cardinal(v)], 1, trail

        # -- names, brands, heteronyms
        plain = strip_okina(core)
        if core in SAY_AS_CASED:
            return [core + PH + SAY_AS_CASED[core]], 1, trail
        if plain.lower() in SAY_AS and plain.replace("-", "").isalpha() and (plain.lower() not in ("kea", "lanai")
                                                            or prev.lower() == "mauna" or plain[0].isupper()):
            return [plain + PH + SAY_AS[plain.lower()]], 1, trail
        pl = prev.lower()
        if low in VERB_FORMS and pl in VERB_BEFORE and (low != "live" or pl in ("i", "eye")) and \
                (low != "present" or pl == "please"):
            return [core + PH + VERB_FORMS[low]], 1, trail
        if low == "close" and (pl in VERB_BEFORE or prev_end) and nxt.lower() in OBJECTS:
            return [core + PH + "klˈOz"], 1, trail
        if low == "bow" and ((pl in ("a", "his", "her", "their", "final") and prev2 in ("take", "took", "takes",
                                                                                          "taking", "a"))
                             or nxt.lower() in ("down", "before", "deeply", "low")):
            return [core + PH + "bˈW"], 1, trail
        if low == "wound" and nxt.lower() in {"up", "down", "around", "round", "through", "back"} | OBJECTS and \
                pl not in ("the", "a", "his", "her", "my", "your", "our", "their", "its", "this", "that", "open",
                           "deep", "fresh", "stab", "gunshot", "head", "old"):
            return [core + PH + "wˈWnd"], 1, trail
        if low == "dove" and (pl in SUBJECTS or nxt.lower() in ("into", "in", "under", "off", "for", "down",
                                                                   "through", "onto", "deep", "headfirst", "back")):
            return [core + PH + "dˈOv"], 1, trail
        if low == "bass" and (pl in ("largemouth", "smallmouth", "striped", "sea", "rock", "peacock")
                              or (pl == "a" and prev2 in ("caught", "catch", "catching", "landed", "hooked"))
                              or nxt.lower() in ("fishing", "fisherman", "boat", "lure", "lures", "pond")):
            return [core + PH + "bˈæs"], 1, trail
        if is_emoji(core):
            return [], 1, trail
        said = self.homograph(core, toks, i)
        if said:
            return [core + PH + said], 1, trail
        return None

    # ---- homographs (v1.2): HOMOGRAPHS, first matching rule wins
    @staticmethod
    def _ctx_word(t: str) -> str:
        a, b = 0, len(t)
        while a < b and t[a] in OPEN:
            a += 1
        while b > a and t[b - 1] in CLOSE:
            b -= 1
        return t[a:b].lower().replace("’", "'")

    def homograph(self, core: str, toks: list[str], i: int) -> str | None:
        """The phonemes of the sense a homograph's context asks for, or None to leave it to the context model."""
        rules = HOMOGRAPHS.get(core.lower())
        if rules is None or not core.isalpha():
            return None
        prev = []                                            # p1, p2, p3 within the clause; "^" before its start
        for j in range(i - 1, i - 4, -1):
            if j < 0 or toks[j][-1:] in HG_STOP:
                prev.append("^")
                break
            prev.append(self._ctx_word(toks[j]))
        nxt = []                                             # n1, n2, n3 within the clause; "$" after its end
        if toks[i][-1:] not in HG_STOP:
            for j in range(i + 1, i + 4):
                if j >= len(toks):
                    nxt.append("$")
                    break
                nxt.append(self._ctx_word(toks[j]))
                if toks[j][-1:] in HG_STOP:
                    break
        if not nxt or len(nxt) < 3 and nxt[-1] != "$":
            nxt.append("$")
        if prev[-1:] != ["^"] and len(prev) < 3:
            prev.append("^")
        cap = core[:1].isupper() and prev[0] != "^"
        for said, tests in rules:
            if all(hg_test(t, prev, nxt, cap) for t in tests):
                return said or None
        return None

    def pairs(self, d: str) -> list[str]:
        """A 4-digit dimension said as two pairs ('1920' -> 19 20), as in screen sizes."""
        if len(d) == 4 and d[2:] != "00" and not d.startswith("0"):
            return [d[:2], d[2:] if d[2] != "0" else "oh " + d[3]]
        return [d]


def roman_value(s: str) -> int:
    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for k, c in enumerate(s):
        v = vals[c]
        total += -v if k + 1 < len(s) and vals[s[k + 1]] > v else v
    return total


def strip_okina(w: str) -> str:
    """Hawaiian spelling folded for lookup: no ʻokina, no kahakō (macrons)."""
    w = re.sub(r"(?<=\w)[ʻ‘'’](?=\w)", "", w)
    return "".join(c for c in unicodedata.normalize("NFD", w) if unicodedata.category(c) != "Mn")


def is_emoji(w: str) -> bool:
    return bool(w) and all(unicodedata.category(c) in ("So", "Sk", "Cf", "Mn") or 0x1F000 <= ord(c) <= 0x1FAFF
                           or c in "️‍" for c in w) and any(0x1F000 <= ord(c) <= 0x1FAFF or
                                                                      0x2600 <= ord(c) <= 0x27BF for c in w)


# ---------------------------------------------------------------- the model

LONG_WORD = 20          # an unknown word longer than this is said in parts (the model loops on long inputs and its
PART = 12               # encoder has 40 positions); a part ends after a vowel, before a consonant, where it can


def split_long(w: str) -> list[str]:
    if len(w) <= LONG_WORD:
        return [w]
    n = -(-len(w) // PART)
    size = len(w) / n
    cuts, last = [], 0
    for k in range(1, n):
        aim = round(k * size)
        best = aim
        for d in (0, 1, -1, 2, -2, 3, -3):
            j = aim + d
            if last < j < len(w) and w[j - 1].lower() in "aeiouy" and w[j].lower() not in "aeiouy":
                best = j
                break
        cuts.append(best)
        last = best
    return [w[a:b] for a, b in zip([0] + cuts, cuts + [len(w)]) if w[a:b]]


# ---------------------------------------------------------------- the lexicon files (1.3)
#
# A .data file: DATA_MAGIC, u32 n + n bytes of JSON (the tables; {} in the words file), then one word section:
#   u32 count, u32 block, u32 len + the words, u32 len + the phonemes                            (little-endian)
# Words are sorted by their UTF-8 bytes and front-coded, each ended by a newline (0x0A): every block-th word is
# written whole, the others as one byte (how many leading bytes it shares with the word before) + the rest.
# Phonemes, one run per word in the same order: the word's symbols (one byte each, an index into the tables'
# "lexiconSymbols") ended by 0xFF, or the single byte 0xFE: in the lexicon and said as the letter-to-sound model
# says it.


def read_data(path: str) -> tuple[dict, dict[str, str | None]]:
    """A .data file -> (its tables, {word: phonemes, or None for a word the letter-to-sound model says})."""
    with open(path, "rb") as f:
        b = f.read()
    if b[:8] != DATA_MAGIC:
        raise SystemExit(f"{path}: not a Leokani G2P 1.3 data file")
    u32 = lambda i: int.from_bytes(b[i:i + 4], "little")  # noqa: E731
    n = u32(8)
    doc = json.loads(b[12:12 + n].decode("utf-8"))
    i = 12 + n
    count, block = u32(i), u32(i + 4)
    i += 8
    parts = []
    for _ in range(2):
        m = u32(i)
        parts.append(b[i + 4:i + 4 + m])
        i += 4 + m
    words, phon = parts
    syms = (doc.get("lexiconSymbols") or symbols_of(path))
    out: dict[str, str | None] = {}
    wi = pi = 0
    prev = b""
    for k in range(count):
        if k % block == 0:
            p = 0
        else:
            p = words[wi]
            wi += 1
        e = words.index(10, wi)
        w = prev[:p] + words[wi:e]
        wi = e + 1
        prev = w
        if phon[pi] == 0xFE:
            out[w.decode("utf-8")] = None
            pi += 1
        else:
            e = phon.index(0xFF, pi)
            out[w.decode("utf-8")] = "".join(syms[c] for c in phon[pi:e])
            pi = e + 1
    return doc, out


def symbols_of(words_path: str) -> list[str]:
    """The words file has no tables of its own: its symbols are leokani-g2p.data's beside it."""
    with open(os.path.join(os.path.dirname(words_path), DATA_FILE), "rb") as f:
        b = f.read()
    n = int.from_bytes(b[8:12], "little")
    return json.loads(b[12:12 + n].decode("utf-8"))["lexiconSymbols"]


class Lexicon:
    """The lexicon: word (lowercase, or as written for the few kept with their case) -> phonemes. A value of None
    means the word is in the lexicon and said as the letter-to-sound model says it (1.3 keeps only the words the
    model gets wrong, plus the common words). The common words come with the tables; the other words file is read
    on the first look-up of a word that is not a common one."""

    def __init__(self, common: dict[str, str | None], words_path: str | None = None, rest=None):
        self.common = common
        self.words_path = words_path
        self._rest = rest

    @property
    def rest(self) -> dict[str, str | None]:
        if self._rest is None:
            self._rest = read_data(self.words_path)[1] if self.words_path else {}
        return self._rest

    @property
    def loaded(self) -> bool:
        return self._rest is not None

    def __contains__(self, w) -> bool:
        return w in self.common or w in self.rest

    def get(self, w, default=None):
        if w in self.common:
            return self.common[w]
        return self.rest.get(w, default)

    def __getitem__(self, w):
        if w in self.common:
            return self.common[w]
        return self.rest[w]

    def __len__(self) -> int:
        return len(self.common) + len(self.rest)

    def __iter__(self):
        yield from self.common
        yield from self.rest


class LeokaniG2P:
    def __init__(self, directory: str = HERE, threads: int = 1, user_lexicon=None, variant: str | None = None,
                 lazy: bool = False):
        """user_lexicon: custom pronunciations, a path (.json or .tsv), a dict or a UserLexicon (see UserLexicon).
        variant: "micro" (default) or "mini", looked up under directory (see VARIANTS).
        lazy: read the other-words file and start each model only when a piece first needs it (default: now)."""
        directory = variant_dir(directory, variant)
        self.directory = directory
        self.variant = variant or DEFAULT_VARIANT
        self.threads = threads
        path = os.path.join(directory, DATA_FILE)
        if os.path.exists(path):
            self.doc, common = read_data(path)
            self.lexicon = Lexicon(common, os.path.join(directory, WORDS_FILE))
            if not lazy:
                self.lexicon.rest
        else:
            path = os.path.join(directory, JSON_FILE)
            with gzip.open(path, "rt", encoding="utf-8") as f:
                self.doc = json.load(f)
            self.lexicon = Lexicon(self.doc["lexicon"], None, {})
        if self.doc.get("format") != FORMAT:
            raise SystemExit(f"{path}: not a {FORMAT} file")
        self.cased: dict[str, str] = self.doc["cased"]
        self.variants: dict[str, list[str]] = self.doc["variants"]
        self.word_ids = {w: i + 2 for i, w in enumerate(self.doc["contextWords"])}
        self.sym_ids = {s: i + 2 for i, s in enumerate(self.doc["symbols"])}
        self.chars = {c: i + 4 for i, c in enumerate(self.doc["chars"])}
        self.out_syms = self.doc["outSymbols"]
        self.numbers = Numbers(self.doc["numberAtoms"], self._word)
        self.symbol_words: dict[str, str] = self.doc["symbolWords"]
        atoms = self.doc["numberAtoms"]
        letters = {k[7:]: v for k, v in atoms.items() if k.startswith("letter:")}
        letters["s"] = "ˈɛs"                                 # the atom is the plural suffix ("80s")
        self.normalizer = Normalizer(lambda w: w in self.lexicon, letters, lambda w: w in self.cased,
                                     lambda w: w in self.word_ids,
                                     lambda w: ([self._lex(w)] if w in self.lexicon else []) + self.variants.get(w, []))
        self._sessions: dict = {}
        if not lazy:
            for k in ONNX_FILES:
                self._session(k)
        self.max_out = int(self.doc["oov"]["maxOut"])
        self.cache: dict[str, str] = {}
        self.user_lexicon = UserLexicon(symbols=set(self.out_syms) | {PRIMARY, SECONDARY})
        self.normalizer.user = self.user_lexicon
        if user_lexicon is not None:
            if isinstance(user_lexicon, (str, os.PathLike)):
                self.load_user_lexicon(os.fspath(user_lexicon))
            else:
                self.user_lexicon.update(user_lexicon)

    # ---- the three models, started on first use when lazy
    def _session(self, key: str):
        if key not in self._sessions:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.intra_op_num_threads = self.threads
            opts.inter_op_num_threads = 1
            self._sessions[key] = ort.InferenceSession(os.path.join(self.directory, ONNX_FILES[key]), opts,
                                                       providers=["CPUExecutionProvider"])
        return self._sessions[key]

    enc = property(lambda self: self._session("enc"))
    dec = property(lambda self: self._session("dec"))
    ctx = property(lambda self: self._session("ctx"))

    def loaded(self) -> list[str]:
        """Which parts are in memory: "words" (the other-words file) and the models ("enc", "dec", "ctx")."""
        return (["words"] if self.lexicon.loaded else []) + [k for k in ONNX_FILES if k in self._sessions]

    # ---- custom pronunciations
    def add_pronunciation(self, word: str, value=None, *, phonemes: str | None = None, say: str | None = None):
        """g2p.add_pronunciation("Leokani", phonemes="lˌAOkˈɑni"); g2p.add_pronunciation("Siobhan", say="shivawn")."""
        self.user_lexicon.add(word, value, phonemes=phonemes, say=say)

    def load_user_lexicon(self, path: str) -> None:
        """Add the custom pronunciations in a .json or .tsv file."""
        self.user_lexicon.load(path)

    # ---- bases
    def _lex(self, lw: str) -> str:
        """The lexicon's phonemes for lowercase word lw (which it has)."""
        v = self.lexicon[lw]
        return self.oov([lw])[0] if v is None else v

    def _word(self, w: str) -> str | None:
        return self.cased.get(w) or (self._lex(w.lower()) if w.lower() in self.lexicon else None)

    def normalize(self, text: str, pauses: bool = True) -> str:
        """A line as a person reads it (see Normalizer); leokani.py calls this before cutting the line up."""
        return self.normalizer(text, pauses)

    def base(self, w: str) -> tuple[str, str]:
        if PH in w:
            return w.split(PH, 1)[1], "lexicon"
        if w in self.cased:
            return self.cased[w], "lexicon"
        lw = w.lower()
        if lw in self.lexicon:
            return self._lex(lw), "lexicon"
        if any(c.isdigit() for c in w):
            said = self.numbers.say(w)
            if said is not None:
                return said, "number"
            # a shape the reader has no rule for ("(212)555-0100", "5'11"): its letter and digit runs, never nothing
            runs = re.findall(r"\d+|[^\W\d_]+", w)
            if runs and runs != [w]:
                return " ".join(b for b in (self.base(r)[0] for r in runs) if b), "number"
        if w in self.symbol_words:
            return self.symbol_words[w], "symbol"
        if not any(c.isalpha() for c in w):
            return "", "empty"
        if w.endswith(".") and w.rstrip(".") and "." not in w.rstrip("."):
            return self.base(w.rstrip("."))                  # "Street." -> Street (an abbreviation's full stop)
        return self.oov([w])[0], "oov"

    def oov(self, words: list[str]) -> list[str]:
        todo = [w for w in words if w not in self.cache]
        if todo:
            parts = {w: split_long(w) for w in todo}
            flat = sorted({p for ps in parts.values() for p in ps})
            said = dict(zip(flat, self._decode(flat)))
            for w in todo:
                self.cache[w] = "".join(said[p] for p in parts[w])
        return [self.cache[w] for w in words]

    def _decode(self, words: list[str]) -> list[str]:
        L = max(len(w) for w in words) + 2
        x = np.zeros((len(words), L), dtype=np.int64)
        for i, w in enumerate(words):
            ids = [2] + [self.chars.get(c, 3) for c in w] + [1]
            x[i, :len(ids)] = ids
        mem, = self.enc.run(None, {"chars": x})
        y = np.full((len(words), 1), 2, dtype=np.int64)            # BOS
        done = np.zeros(len(words), dtype=bool)
        for _ in range(self.max_out):
            logits, = self.dec.run(None, {"memory": mem, "chars": x, "prev": y})
            nxt = logits[:, -1].argmax(-1)
            nxt[done] = 0
            done |= nxt == 1
            y = np.concatenate([y, nxt[:, None]], axis=1)
            if done.all():
                break
        out = []
        for row in y[:, 1:]:
            s = []
            for t in row:
                if t <= 1:
                    break
                s.append(self.out_syms[t - 4] if t >= 4 else "")
            out.append("".join(s))
        return out

    # ---- a piece
    def piece(self, piece: str) -> str:
        return self.piece_words(piece)[0]

    def piece_words(self, piece: str) -> tuple[str, list[str], list[bool], list[str]]:
        """-> (phonemes, each word's form, joins, where each base came from)."""
        words = [w for w in self.normalize(piece, pauses=False).split(" ") if w]
        if not words:
            return "", [], [], []
        oov = [w for w in words if self._needs_oov(w)] + [x for x in map(self._derived, words) if x]
        if oov:
            self.oov(sorted(set(oov)))
        bs = [self.base(w) for w in words]
        bases, srcs = [b for b, _ in bs], [s for _, s in bs]
        given = [PH in w for w in words]                     # said as given: no weak forms of the spelling
        words = [w.split(PH, 1)[0] for w in words]
        feats = features(words, bases, srcs, self.word_ids, self.sym_ids)
        form, join = self.ctx.run(None, {"features": feats[None]})
        forms = []
        for i, (w, b) in enumerate(zip(words, bases)):
            if given[i]:
                logits = form[0, i].copy()
                if not b.endswith("ɹ"):
                    logits[EDGE_OPS.index("linkr")::len(EDGE_OPS)] = -np.inf
                forms.append(pick(logits, candidates(b, [])) or b)
            else:
                forms.append(pick(form[0, i], candidates(b, self.variants.get(w.lower(), []))) or b)
        joins = [bool(join[0, i].argmax()) for i in range(len(words))]
        return assemble(forms, joins), forms, joins, srcs

    def _derived(self, w: str) -> str | None:
        """The lowercase key, when w's base is a lexicon word the letter-to-sound model says (batched with the rest)."""
        if PH in w or w in self.cased:
            return None
        if w.endswith(".") and w.rstrip(".") and "." not in w.rstrip("."):
            w = w.rstrip(".")
        lw = w.lower()
        return lw if lw in self.lexicon and self.lexicon[lw] is None and lw not in self.cache else None

    def _needs_oov(self, w: str) -> bool:
        if w.endswith(".") and w.rstrip(".") and "." not in w.rstrip("."):
            w = w.rstrip(".")
        lw = w.lower()
        return (PH not in w and w not in self.cased and lw not in self.lexicon and w not in self.symbol_words
                and any(c.isalpha() for c in w) and not (any(c.isdigit() for c in w) and self.numbers.say(w)))

    # ---- a whole line
    def phonemize_chunks(self, text: str) -> list[str]:
        """A line or paragraph -> Kokoro phonemes, one string per clause chunk (the unit Leokani-tts speaks), exactly
        as leokani.py's --g2p leokani front end does it: normalise, clean, chunk, split into pieces."""
        return [line(c, self, pieces, desilence) for c in chunks(clean(self.normalize(text)))]

    def phonemize(self, text: str) -> str:
        """A line or paragraph -> one Kokoro phoneme string (the chunks joined by a space)."""
        return " ".join(self.phonemize_chunks(text))

    __call__ = piece
    kokoro = True          # leokani.py: the output is Kokoro phonemes already (no misaki mapping)


# ---------------------------------------------------------------- a whole line, as leokani.py does it

PUNCT = {",", ".", "!", "?", ";", ":", "—", "…"}


def clusters(s: str) -> list[str]:
    out: list[str] = []
    for c in s:
        if out and (unicodedata.category(c) in ("Mn", "Mc", "Me") or c == "‍"):
            out[-1] += c
        else:
            out.append(c)
    return out


def line(text: str, g2p: LeokaniG2P, pieces, prep=None) -> str:
    """pieces: the front end's clause splitter (pieces() below, the same as leokani.py's)."""
    out = ""
    for p in pieces(text):
        if all(c in PUNCT for c in clusters(p)):
            out += p
            continue
        ph = g2p.piece(prep(p) if prep else p)
        if ph == "":
            continue
        if out and not out.endswith(" "):
            out += " "
        out += ph
    return out.strip()


# ---------------------------------------------------------------- the line front end (the same as leokani.py's)

def clean(text: str) -> str:
    """Drop markdown marks and fold whitespace."""
    return re.sub(r"\s+", " ", re.sub(r"[*_`#>|]+", " ", text)).strip()


TITLES = {"dr", "mr", "mrs", "ms", "st", "vs", "etc", "e.g", "i.e", "no", "jr", "sr", "mt"}


def chunks(text: str) -> list[str]:
    """Clause chunks: break after . ! ? ; : (not after a title such as 'Dr.'), and after a comma once a chunk has
    12 words. The first chunk needs 3 words. This is the unit Leokani-tts reads."""
    words = text.split(" ")
    out, cur = [], []
    for w in words:
        if not w:
            continue
        cur.append(w)
        end = w[-1]
        brk = end in "!?;:" or (end == "." and w.lower().strip("(\"'").rstrip(".") not in TITLES) \
            or (end == "," and len(cur) >= 12)
        if brk and len(cur) >= (3 if not out else 1):
            out.append(" ".join(cur))
            cur = []
    if cur:
        out.append(" ".join(cur))
    return [c for c in out if any(ch.isalnum() for ch in c)]


DROPPED = {"\"", "'", "“", "”", "‘", "’", "(", ")", "[", "]", "*", "_", "`", "#"}
ABBREV = {"dr.", "mr.", "mrs.", "ms.", "st.", "jr.", "sr.", "vs.", "etc.", "e.g.", "i.e.", "prof.", "mt.", "no.",
          "a.m.", "p.m.", "u.s.", "approx."}
READ_PAST_BEFORE = {"already", "just", "was", "were", "been", "i've", "we've", "you've", "they've", "had", "has",
                    "have", "never", "once", "recently"}
READ_PAST_AFTER = {"yesterday", "last", "earlier", "ago", "already", "before"}
LEAD_METAL = {"pipe", "pipes", "paint", "poisoning", "pencil", "pencils", "weight", "weights", "shot", "bullet",
              "bullets", "balloon", "acid", "crystal", "apron", "sinker", "solder"}
WIND_VERB_BEFORE = {"to", "will", "would", "can", "could", "must", "should", "please", "i", "we", "you", "they",
                    "and", "don't", "didn't"}
WIND_OBJECT = {"the", "it", "up", "down", "back", "your", "my", "our", "his", "her", "them", "this", "that", "a"}
LIVES_SUBJECT = {"he", "she", "it", "who", "that", "which", "everyone", "someone", "nobody", "one", "anyone",
                 "everybody", "somebody"}
LIVES_OWNER = {"our", "their", "my", "your", "his", "her", "its", "the", "many", "all", "these", "those", "whose",
               "two", "nine", "save", "both"}
YEAR_BEFORE = {"in", "since", "by", "of", "from", "until", "till", "year", "circa", "around", "before", "after",
               "during", "summer", "winter", "spring", "fall", "autumn"}
NAMES = {"tchaikovsky": "chykoffsky", "chopin": "showpan", "goethe": "gerta"}
# The pronoun: espeak-ng leaves 'I' unstressed ('I am' -> 'Iəm'), which comes out as a ~40 ms mumble. These
# spellings give 'ˈI', 'ˈIm', 'ˈIᵊl', 'ˈIv', 'ˈId', stressed, from espeak-ng and Leokani G2P alike.
PRONOUN = {"i": "eye", "i'm": "eim", "i'll": "isle", "i've": "ive", "i'd": "eyed"}
# ...except straight after an auxiliary ('Am I late?', 'Can I ask?'), where the pronoun is weak in speech too.
PRONOUN_AFTER = {"am", "are", "is", "was", "were", "do", "does", "did", "have", "has", "had", "can", "could", "will",
                 "would", "shall", "should", "may", "might", "must", "aren't", "isn't", "wasn't", "weren't",
                 "don't", "doesn't", "didn't", "haven't", "hasn't", "hadn't", "can't", "couldn't", "won't",
                 "wouldn't", "shouldn't", "mustn't"}
# Characters said differently from one platform to the next (Roman numerals, circled letters): read as silent.
SILENT = ((0x2160, 0x2182), (0x2185, 0x2188), (0x24B6, 0x24E9))


def respell(word: str, prev: str | None, nxt: list[str]) -> str | None:
    """The pronoun I, heteronyms and a few names espeak-ng gets wrong, respelled from context."""
    w, p, n = word.lower(), (prev.lower() if prev is not None else None), [x.lower() for x in nxt]
    if word[:1] == "I" and w.replace("’", "'") in PRONOUN:
        return None if p is not None and p.replace("’", "'") in PRONOUN_AFTER else PRONOUN[w.replace("’", "'")]
    if w in NAMES:
        return NAMES[w]
    if w == "read":
        if (p is not None and p in READ_PAST_BEFORE) or any(x in READ_PAST_AFTER for x in n):
            return "red"
    elif w == "lead":
        if (n and n[0] in LEAD_METAL) or p == "of":
            return "led"
    elif w in ("wind", "winds"):
        s = "s" if w == "winds" else ""
        if n and n[0] in ("up", "down"):
            return "wined" + s
        if n and n[0] in WIND_OBJECT and (p is None or p in WIND_VERB_BEFORE):
            return "wined" + s
    elif w == "lives":
        if p is not None and p in LIVES_SUBJECT:
            return "livs"
        if p is not None and prev and prev[0].isupper() and p not in LIVES_OWNER:
            return "livs"
    if p is not None and p in YEAR_BEFORE and len(w) == 4 and w.isascii() and w.isdigit():
        y = int(w)
        if 1100 <= y <= 1999 or 2010 <= y <= 2099:
            hi, lo = y // 100, y % 100
            return f"{hi} hundred" if lo == 0 else f"{hi} oh {lo}" if lo < 10 else f"{hi} {lo}"
    return None


def pieces(text: str) -> list[str]:
    """Words grouped into punctuation-free clauses, with the punctuation marks between them as their own pieces."""
    words: list[tuple[str, str]] = []
    for t in text.split():
        core = clusters(t)
        while core and core[0] in DROPPED:
            core = core[1:]
        trail = ""
        while core and (core[-1] in DROPPED or core[-1] in PUNCT):
            last = core[-1]
            if last in PUNCT:
                if last == "." and "".join(core).lower() in ABBREV:
                    break
                trail = last + trail
            core = core[:-1]
        if core and all(c == "-" for c in core):
            words.append(("", "—"))
            continue
        words.append(("".join(core), trail))
    out: list[str] = []
    clause: list[str] = []
    for i, (word, punct) in enumerate(words):
        if word:
            prev = words[i - 1][0] if i > 0 and words[i - 1][1] == "" else None
            nxt: list[str] = []
            if punct == "":
                for j in range(i + 1, min(len(words), i + 5)):
                    nxt.append(words[j][0])
                    if words[j][1] != "":
                        break
            r = respell(word, prev, nxt)
            clause.append(r if r is not None else word)
        if punct:
            if clause:
                out.append(" ".join(clause))
            clause = []
            out.append("…" if ".." in punct else "".join(clusters(punct)[:2]))
    if clause:
        out.append(" ".join(clause))
    return out


def desilence(piece: str) -> str:
    """Characters in SILENT become spaces, as leokani.py's Leokani G2P front end does before each piece."""
    return "".join(" " if any(a <= ord(c) <= b for a, b in SILENT) else c for c in piece)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Leokani G2P: English to Kokoro-style phonemes.")
    ap.add_argument("piece", nargs="?", help="one clause (no punctuation); default: read lines from stdin")
    ap.add_argument("--text", help="a whole line, split into clauses as leokani.py does")
    ap.add_argument("--model", default=HERE, help="directory with the lexicon (.data) and the .onnx files")
    ap.add_argument("--variant", choices=list(VARIANTS), default=DEFAULT_VARIANT, help="model size (default micro)")
    ap.add_argument("--lexicon", action="append", default=[], help="custom pronunciations (.json or .tsv)")
    a = ap.parse_args(argv)
    g = LeokaniG2P(a.model, variant=a.variant)
    for path in a.lexicon:
        g.load_user_lexicon(path)
    if a.text is not None:
        print(g.phonemize(a.text))
        return 0
    for p in ([a.piece] if a.piece is not None else (ln.rstrip("\n") for ln in sys.stdin)):
        print(g.piece(p))
    return 0


if __name__ == "__main__":
    sys.exit(main())
