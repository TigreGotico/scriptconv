"""One word: CMUdict pronunciation -> phones of the inventory.

CMUdict writes a broad phonemic transcription (39 phonemes, stress digits on
the vowels). The TTS model was trained on a narrower one: flaps, a glottal
stop before syllabic n, r-coloured vowels as single phones, syllabic l, several
reduced vowels. This module adds what CMUdict lacks, by rule.

Many of the rules depend on how the vowel is written (the reduced vowel of
"cabin" is not that of "sofa"; "more" and "for" differ), so they work on the
pronunciation aligned to the spelling (``align.Aligner``). Without an alignment
the spelling-dependent rules fall back to their default.

The result is the citation form of the word. What depends on neighbouring
words (linking r, a flap at the end of "it" before a vowel, weak forms) is in
``sentence.py``.
"""

from .symbols import PHONE_SET, VOWEL_SET
from .align import base

ARPA_VOWELS = frozenset("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split())
CONSONANTS = {"B": "b", "CH": "tʃ", "D": "d", "DH": "ð", "F": "f", "G": "ɡ", "HH": "h", "JH": "dʒ", "K": "k", "L": "l",
              "M": "m", "N": "n", "NG": "ŋ", "P": "p", "R": "ɹ", "S": "s", "SH": "ʃ", "T": "t", "TH": "θ", "V": "v",
              "W": "w", "Y": "j", "Z": "z", "ZH": "ʒ"}
FULL_VOWELS = {"AA": "ɑː", "AE": "æ", "AH": "ʌ", "AO": "ɔː", "AW": "aʊ", "AY": "aɪ", "EH": "ɛ", "ER": "ɜː", "EY": "eɪ",
               "IH": "ɪ", "IY": "iː", "OW": "oʊ", "OY": "ɔɪ", "UH": "ʊ", "UW": "uː"}
ARPABET = frozenset(CONSONANTS) | frozenset(v + d for v in ARPA_VOWELS for d in "012")
SIBILANTS = frozenset(("S", "Z", "SH", "ZH", "CH", "JH"))
STRESS_MARKS = {1: "ˈ", 2: "ˌ"}
_VOWEL_LETTERS = frozenset("aeiouy")
# Words of the FORCE set written "or" before a consonant (Wells's lexical sets):
# they keep the closer vowel that "more" and "four" have.
_FORCE_SPELLINGS = ("forc", "ford", "sword", "worn", "torn", "sworn", "borne", "shorn", "pork", "divorc")
_PREFIXES = ("dis", "mis", "un", "in", "re", "non", "over", "pre")
_WEAK_PREFIXES = ("be", "de", "re", "pre")
_IRE_ENDINGS = ("ing", "ings", "ingly", "able", "y", "er", "ers", "est")

assert all(p in PHONE_SET for p in list(CONSONANTS.values()) + list(FULL_VOWELS.values())
           + ["ə", "ɐ", "ɚ", "ᵻ", "i", "ɔ", "oː", "iə", "ɑːɹ", "ɔːɹ", "oːɹ", "ɪɹ", "ɛɹ", "ʊɹ", "aɪɚ", "aɪə", "əl", "n̩", "ɾ", "ʔ"])


def is_arpabet(symbols):
    return bool(symbols) and all(s in ARPABET for s in symbols)


def vowel_letters(run):
    return "".join(c for c in run if c in _VOWEL_LETTERS)


def to_text(phones):
    """``[(phone, stress), ...]`` -> ``"h ə l ˈoʊ"``."""
    return " ".join(STRESS_MARKS.get(stress, "") + phone for phone, stress in phones)


def from_text(text):
    """``"h ə l ˈoʊ"`` -> ``((phone, stress), ...)``; raises on a symbol outside the inventory."""
    phones = []
    for unit in text.split():
        stress = 1 if unit[0] == "ˈ" else 2 if unit[0] == "ˌ" else 0
        phone = unit[1:] if stress else unit
        if phone not in PHONE_SET:
            raise ValueError(f"{phone!r} is not a phone of the inventory")
        if stress and phone not in VOWEL_SET:
            raise ValueError(f"stress mark on the consonant {phone!r}")
        phones.append((phone, stress))
    return tuple(phones)


class _Word:
    """The aligned pronunciation of one word and the questions the rules ask of it."""

    def __init__(self, word, arpabet, runs):
        self.word = word
        self.bases = [base(s) for s in arpabet]
        self.stress = [int(s[-1]) if s[-1] in "012" else None for s in arpabet]
        for symbol, name in zip(arpabet, self.bases):
            if name not in CONSONANTS and name not in ARPA_VOWELS:
                raise ValueError(f"{symbol!r} is not an ARPABET symbol")
        self.aligned = runs is not None
        self.runs = list(runs) if runs is not None else [""] * len(arpabet)
        self.starts, position = [], 0
        for run in self.runs:
            self.starts.append(position)
            position += len(run)
        self.count = len(self.bases)

    def base(self, i):
        return self.bases[i] if 0 <= i < self.count else None

    def vowel(self, i):
        return 0 <= i < self.count and self.bases[i] in ARPA_VOWELS

    def unstressed(self, i):
        return self.vowel(i) and not self.stress[i]

    def letters(self, i):
        return vowel_letters(self.runs[i])

    def before(self, i):
        """Spelling that precedes the letters of segment ``i``."""
        return self.word[:self.starts[i]] if self.aligned else ""

    def after(self, i):
        """Spelling that follows the letters of segment ``i``."""
        return self.word[self.starts[i] + len(self.runs[i]):] if self.aligned else ""

    def ends_with(self, i, *symbols):
        """True when exactly ``symbols`` follow segment ``i`` to the end of the word."""
        return tuple(self.bases[i + 1:]) == symbols

    def first_vowel(self, i):
        return not any(b in ARPA_VOWELS for b in self.bases[:i])

    def next_vowel_stress(self, i):
        for j in range(i + 1, self.count):
            if self.bases[j] in ARPA_VOWELS:
                return self.stress[j]
        return None

    def weak_prefix(self, i):
        """Segment ``i`` is the "e" of an unstressed be-, de-, re- or pre-."""
        return self.aligned and self.first_vowel(i) and self.letters(i) == "e" and self.word.startswith(_WEAK_PREFIXES) \
            and self.before(i) in ("b", "d", "r", "pr")


def _north_or_force(w, i, before_vowel):
    """AO + R: ``"oː"`` for the FORCE set (more, four, door, port, story),
    ``"ɔː"`` for NORTH (for, short, war). General American merges them; the
    model has both tokens, so the choice follows the spelling."""
    if not w.aligned:
        return "ɔː"
    spelled = w.letters(i)
    if spelled in ("oa", "oo", "ou"):
        return "oː"
    if spelled != "o":
        return "ɔː"
    run = w.runs[i]
    tail = run[run.find("o") + 1:] + w.after(i)      # the letters after the "o", normally starting with "r"
    rest = tail[1:]
    if not before_vowel:
        if rest.startswith("e"):                     # more, store, before, ignored
            return "oː"
        if w.before(i).endswith("p") and rest.startswith("t"):      # port, support, important
            return "oː"
        return "oː" if any(s in w.word for s in _FORCE_SPELLINGS) else "ɔː"
    if rest.startswith("r"):                         # horror, torrent
        return "ɔː"
    if rest in ("y", "ies", "ied", "a", "as", "ah", "er", "ers") or rest.startswith(("ia", "io", "iu", "ing", "age")):
        return "oː"                                  # story, flora, memorial, boring, storage
    return "ɔː"


def _weak_i(w, i):
    """A reduced vowel written "i": the barred i of "possible", "quality" and
    "terrify", the happy vowel of "beautiful", otherwise ɪ."""
    nxt, nxt2 = w.base(i + 1), w.base(i + 2)
    if nxt == "F" and nxt2 == "AH" and w.base(i + 3) == "L":
        return "i"
    if (nxt == "T" and nxt2 == "IY") or (nxt == "B" and nxt2 in ("AH", "L")) or (nxt == "F" and nxt2 == "AY"):
        return "ᵻ"
    if nxt == "T" and w.ends_with(i, "T") and w.base(i - 1) in ("R", "ER") and w.word.endswith("ite"):
        return "ᵻ"                                   # favorite
    return "ɪ"


def _weak_e(w, i):
    """A reduced vowel written "e" outside a weak prefix."""
    nxt, prev = w.base(i + 1), w.base(i - 1)
    if nxt == "T" and (w.ends_with(i, "T") or w.ends_with(i, "T", "S")):
        return "ə" if prev == "L" else "ᵻ" if prev == "R" else "ɪ"      # bracelet; secret; pocket, basket
    if nxt == "S" and (w.ends_with(i, "S", "T") or w.ends_with(i, "S", "T", "L", "IY")):
        return "ɪ"                                   # nearest, honest, honestly
    if nxt == "JH":
        return "ɪ"                                   # college, knowledge
    if nxt == "K" and w.base(i + 2) == "T":
        return "ɛ"                                   # perfect, subject
    if nxt == "D" and w.ends_with(i, "D"):
        return "ɪ"                                   # naked, wicked
    return "ə"


def _inflection(w, i):
    """The vowel of "-ed" after t/d and of "-es" after a sibilant."""
    if i + 1 >= w.count or (w.aligned and "e" not in w.runs[i] + w.runs[i + 1]):
        return False
    nxt, prev = w.base(i + 1), w.base(i - 1)
    if nxt == "D" and prev in ("T", "D") and (w.ends_with(i, "D") or w.ends_with(i, "D", "L", "IY")):
        return True
    return nxt == "Z" and prev in SIBILANTS and w.ends_with(i, "Z")


def _first_syllable(w, i):
    """An unstressed first vowel right before the stressed syllable: the weak
    prefixes of "before", "return", "expect", "enjoy". ``None`` if no rule applies."""
    if not w.aligned or not w.first_vowel(i) or not w.next_vowel_stress(i):
        return None
    word = w.word
    if i == 0 and word.startswith("e"):
        if word.startswith("ex"):
            return "ɛ"
        if word[1:2] in ("n", "m", "s") and word[2:3] and word[2] not in _VOWEL_LETTERS and word[2] != word[1]:
            return "ɛ"                               # enjoy, embrace, escape
        return "ɪ"                                   # eleven, effect, enough
    if w.weak_prefix(i):
        if word.startswith("pre") or (word.startswith("be") and word[2:3] in ("c", "g")):
            return "ɪ"                               # prevent; because, began
        return "ᵻ"                                   # before, return, decide
    if w.letters(i) == "i" and word.startswith("di") and len(word) > 3 and word[2] not in _VOWEL_LETTERS \
            and word[2] != "s" and word[3] in _VOWEL_LETTERS:
        return "ᵻ"                                   # divide, direct
    return None


def _reduced(w, i):
    """Quality of an unstressed AH or IH."""
    name, spelled = w.bases[i], w.letters(i)
    nxt, prev = w.base(i + 1), w.base(i - 1)
    if name == "IH" and nxt == "NG":
        return "ɪ"
    if _inflection(w, i):
        return "ᵻ"
    if name == "AH":
        if prev == "Y" and "u" in w.runs[i - 1] + w.runs[i]:
            return "ʊ"                               # popular, document
        if i == 0 and w.word.startswith("a"):
            return "ɐ"                               # about, again
        if i == 0 and nxt == "N" and w.word.startswith("un"):
            return "ʌ"                               # until, unhappy
        if spelled == "a" and w.before(i) in _PREFIXES and w.runs[i].startswith("a"):
            return "ɐ"                               # disappoint, inability
    prefix = _first_syllable(w, i)
    if prefix:
        return prefix
    if spelled == "e" and nxt in ("K", "G") and w.runs[i + 1].startswith("x") and w.next_vowel_stress(i):
        return "ɛ"                                   # unexpected, inexperienced
    if spelled in ("i", "ai", "ui", "y"):
        return _weak_i(w, i)
    if spelled == "e":
        return _weak_e(w, i)
    if spelled == "a":
        if nxt == "JH" or (nxt == "N" and w.base(i + 2) == "JH"):
            return "ɪ"                               # village, orange
        if nxt == "S" and w.ends_with(i, "S") and w.word.endswith("ace"):
            return "ɪ"                               # palace, surface
        if name == "IH" and not (nxt == "T" and w.ends_with(i, "T")):
            return "ɪ"                               # character; but private
        return "ə"
    if name == "AH" and nxt == "M" and w.ends_with(i, "M") and w.word.endswith("ome"):
        return "ʌ"                                   # handsome, welcome
    return "ɪ" if name == "IH" and spelled not in ("o", "u", "ou") else "ə"


def _unstressed_iy(w, i):
    nxt = w.base(i + 1)
    if nxt is None or w.ends_with(i, "Z") or w.ends_with(i, "D"):
        return "i", 0                                # happy, stories, married
    if w.vowel(i + 1):
        return ("i" if nxt == "IH" and w.base(i + 2) == "NG" else "ɪ"), 0      # carrying; video, earlier
    if w.weak_prefix(i):
        return ("ᵻ", 0) if w.next_vowel_stress(i) == 1 else ("iː", 2)          # remind; reconsider
    return "ɪ", 0                                    # anything, happiness


def convert(word, arpabet, runs=None):
    """Citation form of ``word`` as ``((phone, stress), ...)``.

    ``arpabet`` is a CMUdict pronunciation (symbols with stress digits) and
    ``runs`` the letters aligned to each symbol, or ``None``.
    """
    w = _Word(word, list(arpabet), runs)
    out = []                                         # [phone, stress]
    emit = lambda phone, stress=0: out.append([phone, stress or 0])
    i = 0
    while i < w.count:
        name, stress = w.bases[i], w.stress[i] or 0
        nxt = w.base(i + 1)
        if name not in ARPA_VOWELS:
            if name == "Y" and nxt == "AH" and w.unstressed(i + 1) and w.base(i - 1) in ("N", "L") and w.base(i + 2) != "L" \
                    and (not w.aligned or "i" in w.runs[i] + w.runs[i + 1]):
                emit("iə")                           # opinion, million, brilliant
                i += 2
                continue
            emit(CONSONANTS[name])
            i += 1
            continue
        before_vowel = w.vowel(i + 2)                # only meaningful when the next segment is R
        if name == "ER":
            emit("ɜː" if stress else "ɚ", stress)
            if nxt == "R":
                i += 1
            if w.vowel(i + 1):
                emit("ɹ")                            # around, history
        elif nxt == "R" and name == "AW":
            emit("aʊ", stress)                       # hour, flour
            emit("ɚ")
            if before_vowel:
                emit("ɹ")
            i += 1
        elif nxt == "R" and name in ("AA", "AO", "IH", "IY", "EH", "UH", "UW", "AY"):
            if name == "AA":
                quality, single = "ɑː", "ɑːɹ"
            elif name == "AO":
                quality = _north_or_force(w, i, before_vowel)
                single = quality + "ɹ"
            elif name in ("IH", "IY"):
                quality = "iə" if stress and w.letters(i) in ("e", "eo") else "ɪ"      # zero, period; hearing, spirit
                single = "ɪɹ"
            elif name == "EH":
                doubled = (w.runs[i + 1] + w.after(i + 1)).startswith("rr") or w.runs[i].endswith("r") and w.runs[i + 1].startswith("r")
                quality, single = ("æ" if w.letters(i) == "a" and doubled else "ɛ"), "ɛɹ"      # marry; very
            elif name in ("UH", "UW"):
                quality = single = "ʊɹ"              # "during" keeps the r-coloured vowel and adds ɹ
            else:
                quality, single = ("aɪɚ" if not w.aligned or w.after(i + 1) in _IRE_ENDINGS else "aɪ"), "aɪɚ"      # hiring; pirate
            if before_vowel:
                emit(quality, stress)
                emit("ɹ")
            else:
                emit(single, stress)
            i += 1
        elif name == "AY" and nxt == "ER" and w.unstressed(i + 1) and w.runs[i + 1] == "er" and w.runs[i] != "i":
            emit("aɪ", stress)                       # higher, buyer, flyer: a word plus "-er"
        elif name == "AY" and nxt == "ER" and w.unstressed(i + 1):
            emit("aɪɚ", stress)                      # fire, tired, iron
            i += 1
            if w.vowel(i + 1):
                emit("ɹ")
        elif name == "AY" and nxt == "AH" and w.unstressed(i + 1):
            emit("aɪə", stress)                      # quiet, society
            i += 1
        elif name == "IY" and nxt == "AH" and w.unstressed(i + 1) and not w.weak_prefix(i):
            after = w.base(i + 2)
            if stress != 1 and (after in ("L", "D", "T") or (after == "N" and w.base(i + 3) == "S")):
                emit("ɪ")                            # material, period, immediate, experience
            else:
                emit("iə", stress)                   # idea, various, museum
                i += 1
        elif not stress and name == "AH" and nxt == "N" and w.base(i - 1) == "T" and w.base(i + 2) != "T" \
                and len(out) >= 2 and out[-1][0] == "t" and out[-2][0] in VOWEL_SET and out[-2][1]:
            out[-1][0] = "ʔ"                         # button, certain, frightened
            emit("n̩")
            i += 1
        elif not stress and name == "AH" and nxt == "W" and w.base(i + 2) == "AH" and w.unstressed(i + 2) \
                and "u" in w.runs[i] + w.runs[i + 1]:
            emit("uː")                               # usual, individual: the "u" of "-ual"
            i += 1
        elif not stress and name == "AH" and nxt == "L" and i > 0 and not (w.vowel(i + 2) and w.stress[i + 2]):
            if w.letters(i) == "i" and w.vowel(i + 2):
                emit("ɪ")                            # family, easily
            elif w.base(i - 1) == "Y" and "u" in w.runs[i - 1] + w.runs[i]:
                emit("ʊ")                            # popular, regular
            else:
                emit("əl")                           # little, finally
                i += 1
        elif not stress and name in ("AH", "IH"):
            emit(_reduced(w, i))
        elif name == "IY" and (not stress or (stress == 2 and nxt is None)):
            emit(*_unstressed_iy(w, i))
        elif not stress and name == "AE" and i == 0 and w.word.startswith(("ad", "acc")) and nxt in ("D", "K"):
            emit("ɐ")                                # advice, accept
        elif not stress and name == "ER":
            emit("ɚ")
        elif name in ("AA", "AO") and w.letters(i) == "a" and w.before(i).endswith(("w", "qu")) and nxt == "N":
            emit("ɔ", stress)                        # want, quantity
        elif name == "AO" and w.letters(i) == "o":
            emit("ɔ", stress)                        # long, off, lost
        else:
            emit(FULL_VOWELS[name], stress)
        i += 1
    _flap(out)
    for k in range(len(out) - 1):
        if out[k][0] == "n" and out[k + 1][0] in ("k", "ɡ"):
            out[k][0] = "ŋ"                          # income, engaged
    _settle_stress(out)
    return tuple((phone, stress) for phone, stress in out)


def _flap(out):
    """t between a vowel (or r) and an unstressed vowel: water, city, party."""
    for k in range(1, len(out) - 1):
        if out[k][0] != "t":
            continue
        before, (after, stress) = out[k - 1][0], out[k + 1]
        if (before not in VOWEL_SET and before != "ɹ") or before in ("n̩", "əl") or after not in VOWEL_SET or after == "n̩":
            continue
        # A word-final "o" is weak whatever stress digit CMUdict gives it: potato, photo.
        final_o = after == "oʊ" and (k + 2 == len(out) or (k + 3 == len(out) and out[k + 2][0] == "z"))
        if stress and not final_o:
            continue
        if after in ("ə", "ɚ") and k + 2 < len(out) and out[k + 2][0] == "n":
            continue                                 # skeleton, important, pattern
        out[k][0] = "ɾ"


def settle_stress(phones):
    """``_settle_stress`` for a finished pronunciation (compounds, prefixed words)."""
    out = [[phone, stress] for phone, stress in phones]
    _settle_stress(out)
    return tuple((phone, stress) for phone, stress in out)


def _settle_stress(out):
    """One primary stress per word, and no secondary stress on a syllable next
    to the primary one (weekend, notebook, important)."""
    vowels = [k for k, (phone, _) in enumerate(out) if phone in VOWEL_SET]
    primaries = [k for k in vowels if out[k][1] == 1]
    for k in primaries[:-1]:
        out[k][1] = 2
    for position, k in enumerate(vowels):
        if out[k][1] != 2:
            continue
        neighbours = [vowels[p] for p in (position - 1, position + 1) if 0 <= p < len(vowels)]
        if any(out[n][1] == 1 for n in neighbours):
            out[k][1] = 0
