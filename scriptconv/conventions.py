"""Orthographic conventions — script-scoped decorations, orthogonal to identity.

Scripts are text *identity*: character-evident, ISO-15924-coded, the nodes of
scriptconv's conversion space (:mod:`scriptconv.scripts`).  Conventions are
*decorations* a script's orthography can carry or omit — optional vocalization
(Arabic tashkeel, Hebrew niqqud), justification (kashida), spacing modes
(Japanese wakachigaki), or mutually-exclusive spellings of the same
information (pinyin tone marks vs digits).  A convention never participates in
script detection or conversion routing; it is always a parameter, never a
node.

Each convention declares its *styles* — the mutually exclusive states its text
can be in.  Binary decorations have styles ``("marked", "none")``; variant
conventions name their spellings (``("mark", "number", "none")``).  The one
real operation is :func:`restyle`, a partial transition matrix between styles;
:func:`strip` and :func:`apply` are sugar for transitions to and from
``"none"``.

Which transitions exist follows the same boundary the rest of scriptconv
draws:

* stripping and deterministic re-spelling are pure orthography — always
  available, zero-dependency;
* transitions that need a *dictionary lookup* (wakachigaki application =
  word segmentation) are orthography too, but live behind the optional
  extras, like :mod:`scriptconv.readings`;
* transitions that need contextual *prediction* (restoring tashkeel or
  niqqud, i.e. diacritization) are linguistic inference, out of scope for the
  same reason grapheme-to-phoneme is.  Their absence is queryable data, not a
  runtime surprise.

What is **not** a convention: marks that are letter identity rather than
decoration.  Vietnamese tone diacritics spell different words, Arabic
hamza/madda (U+0653–U+0655) distinguish letters, and stripping them corrupts
text — none are registered.  Casing on bicameral scripts *is* a convention in
the sense used here, but the stdlib (``str.lower``/``str.casefold``) already
models it correctly, so it is deliberately not duplicated.

``jamo-form`` is the registry's one documented impurity: compatibility vs
conjoining jamo is a Unicode *representation* convention rather than an
orthographic one, registered because free text genuinely occurs in both
repertoires and the restyle is deterministic.
"""
from __future__ import annotations

import functools
import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

__all__ = [
    "Convention",
    "Transition",
    "CONVENTION_REGISTRY",
    "conventions_for",
    "detect",
    "restyle",
    "strip",
    "apply",
]


@dataclass(frozen=True)
class Transition:
    """One rewrite between two styles of a convention.

    ``fn`` is a pure ``str -> str`` transform.  ``requires`` names the
    optional extra the transform needs, if any (queryable before calling —
    the transform itself raises :class:`ImportError` with an install hint
    when the dependency is missing).
    """
    frm: str
    to: str
    fn: Callable[[str], str]
    lossless: bool = False
    requires: Optional[str] = None


@dataclass(frozen=True)
class Convention:
    """One orthographic convention: metadata plus the behavior that owns it.

    Transitions and the optional detector live on the convention itself, so
    every operation is generic — nothing in this module branches on a
    convention's identity.
    """
    id: str
    name: str
    scripts: Tuple[str, ...]           # ISO-15924 codes whose text it decorates
    system: Optional[str]              # sub-script system qualifier ("pinyin", "japanese")
    styles: Tuple[str, ...]            # mutually exclusive states; includes "none" if strippable
    default_style: str
    ranges: Tuple[Tuple[int, int], ...]  # decoration codepoints (empty for spacing/variant conventions)
    reference: str
    transitions: Tuple[Transition, ...] = ()
    detector: Optional[Callable[[str], Optional[str]]] = None

    @property
    def detectable(self) -> bool:
        return self.detector is not None

    @property
    def strip_lossless(self) -> bool:
        stripping = [t for t in self.transitions if t.to == "none"]
        return bool(stripping) and all(t.lossless for t in stripping)

    @property
    def apply_requires(self) -> Optional[str]:
        return next((t.requires for t in self.transitions if t.frm == "none"), None)

    def transition(self, frm: str, to: str) -> Optional[Transition]:
        return next((t for t in self.transitions
                     if t.frm == frm and t.to == to), None)

    def restyle(self, text: str, to: str, frm: Optional[str] = None) -> str:
        """Rewrite *text* from one style of this convention to another."""
        if to not in self.styles and to != "none":
            raise ValueError(f"{self.id!r} has styles {self.styles}, not {to!r}")
        if frm is None:
            frm = self._infer_source(text, to)
        if frm == to:
            return text
        t = self.transition(frm, to)
        if t is None:
            supported = sorted(f"{x.frm}->{x.to}" for x in self.transitions)
            raise ValueError(f"{self.id!r} does not define {frm!r}->{to!r}; "
                             f"supported: {', '.join(supported)}")
        return t.fn(text)

    def _infer_source(self, text: str, to: str) -> str:
        if self.detector is not None:
            detected = self.detector(text)
            if detected is not None and (detected == to
                                         or self.transition(detected, to)):
                return detected
        sources = sorted({t.frm for t in self.transitions if t.to == to})
        if len(sources) == 1:
            return sources[0]
        if self.default_style != to:
            return self.default_style
        raise ValueError(f"{self.id!r}: source style for ->{to!r} is ambiguous "
                         f"({', '.join(sources)}); pass frm=")

    def strip(self, text: str) -> str:
        """Remove this convention's decoration (restyle to ``"none"``)."""
        stripping = [t for t in self.transitions if t.to == "none"]
        if not stripping:
            raise ValueError(f"{self.id!r} has no unmarked style; "
                             f"styles: {self.styles}")
        # when every stripping transition is the same transform (e.g. one
        # strip handles both pinyin tone spellings), the source is irrelevant
        if len({t.fn for t in stripping}) == 1:
            return stripping[0].fn(text)
        return self.restyle(text, "none")

    def apply(self, text: str, style: Optional[str] = None) -> str:
        """Add this convention's decoration to unmarked text."""
        if style is None:
            marked = [s for s in self.styles if s != "none"]
            style = self.default_style if self.default_style != "none" else marked[0]
        return self.restyle(text, style, frm="none")

    def detect(self, text: str) -> Optional[str]:
        """Current style of *text*, or None when not character-evident.

        For binary decorations this means "any mark present" — a single
        shadda in a paragraph reports ``"marked"``.
        """
        return self.detector(text) if self.detector is not None else None


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _in_ranges(cp: int, ranges: Tuple[Tuple[int, int], ...]) -> bool:
    return any(lo <= cp <= hi for lo, hi in ranges)


def _range_strip(ranges: Tuple[Tuple[int, int], ...]) -> Callable[[str], str]:
    def _strip(text: str) -> str:
        return "".join(c for c in text if not _in_ranges(ord(c), ranges))
    return _strip


def _range_detector(ranges: Tuple[Tuple[int, int], ...]) -> Callable[[str], Optional[str]]:
    def _detect(text: str) -> Optional[str]:
        return "marked" if any(_in_ranges(ord(c), ranges) for c in text) else "none"
    return _detect


# ---------------------------------------------------------------------------
# Wakachigaki
# ---------------------------------------------------------------------------
# Strip removes space runs only when BOTH flanks are Japanese-class: spaces
# next to Latin, digits or boundaries carry information ("きょうは good day",
# "第 3 章") and must survive.

def _is_japanese_flank(ch: str) -> bool:
    cp = ord(ch)
    return (0x3041 <= cp <= 0x309F or          # hiragana
            0x30A0 <= cp <= 0x30FF or          # katakana incl. ー
            0x31F0 <= cp <= 0x31FF or          # katakana phonetic extensions
            0xFF66 <= cp <= 0xFF9F or          # halfwidth katakana
            0x4E00 <= cp <= 0x9FFF or          # CJK unified
            0x3400 <= cp <= 0x4DBF or          # CJK ext A
            cp in (0x3005, 0x3006, 0x303B))    # 々 〆 repeat marks

_WAKACHI_SPACE = re.compile(r"[ 　]+")


def _wakachigaki_strip(text: str) -> str:
    out = []
    i = 0
    while i < len(text):
        m = _WAKACHI_SPACE.match(text, i)
        if m:
            before = out[-1] if out else ""
            after = text[m.end():m.end() + 1]
            if not (before and after and _is_japanese_flank(before[-1])
                    and _is_japanese_flank(after)):
                out.append(m.group(0))
            i = m.end()
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _wakachigaki_apply(text: str) -> str:
    try:
        from scriptconv.readings import tokens
    except ImportError:
        raise ImportError(
            "applying wakachigaki needs dictionary word segmentation — "
            "install with `pip install scriptconv[ja]`") from None
    parts: List[str] = []
    for tok in tokens(text):
        if parts and _is_japanese_flank(parts[-1][-1]) and _is_japanese_flank(tok.orig[0]):
            parts.append(" ")
        parts.append(tok.orig)
    return "".join(parts)


# ---------------------------------------------------------------------------
# Pinyin tone spelling
# ---------------------------------------------------------------------------
# number→mark is deterministic.  mark→number is deterministic for GB/T
# 16159-compliant (apostrophized) pinyin; on non-compliant input where several
# marked vowels share one letter run, syllables are split best-effort before
# the longest valid onset preceding each subsequent marked vowel.

_TONE_COMBINING = {1: "̄", 2: "́", 3: "̌", 4: "̀"}
_COMBINING_TONE = {v: k for k, v in _TONE_COMBINING.items()}
_VOWELS = "aeiouü"
_ONSETS = {"b", "p", "m", "f", "d", "t", "n", "l", "g", "k", "h",
           "j", "q", "x", "r", "z", "c", "s", "y", "w", "zh", "ch", "sh"}


def _mark_syllable(syl: str, tone: int) -> str:
    """Place the tone mark of *syl* (tone digit already removed)."""
    syl = syl.replace("v", "ü").replace("V", "Ü").replace("u:", "ü").replace("U:", "Ü")
    if tone in (0, 5):
        return syl
    low = syl.lower()
    pos = -1
    if "a" in low:
        pos = low.index("a")
    elif "e" in low:
        pos = low.index("e")
    elif "ou" in low:
        pos = low.index("o")
    else:
        for i in range(len(low) - 1, -1, -1):
            if low[i] in _VOWELS:
                pos = i
                break
    if pos == -1:  # syllabic nasal (m, n, ng, hm, hng): mark the first nasal
        for i, c in enumerate(low):
            if c in "mn":
                pos = i
                break
    if pos == -1:
        return syl
    marked = unicodedata.normalize(
        "NFC", syl[:pos + 1] + _TONE_COMBINING[tone] + syl[pos + 1:])
    return marked


_NUM_SYL = re.compile(r"([a-zA-ZüÜ:]+)([0-5])")


def _pinyin_number_to_mark(text: str) -> str:
    return _NUM_SYL.sub(lambda m: _mark_syllable(m.group(1), int(m.group(2))), text)


def _split_run(run: str) -> List[str]:
    """Split one letter run into syllables, one tone mark each (best effort)."""
    decomp = unicodedata.normalize("NFD", run)
    mark_positions = [i for i, c in enumerate(decomp) if c in _COMBINING_TONE]
    if len(mark_positions) <= 1:
        return [run]
    cuts = []
    for mp in mark_positions[1:]:
        # walk back over the marked vowel's preceding consonant cluster and
        # cut before the longest valid onset
        j = mp - 1
        while j >= 0 and decomp[j] in _COMBINING_TONE:
            j -= 1
        # j is the vowel carrying the mark; find start of consonant cluster
        k = j
        while k > 0 and decomp[k - 1].lower() not in _VOWELS \
                and decomp[k - 1] not in _COMBINING_TONE:
            k -= 1
        cluster = decomp[k:j]
        cut = j
        for size in (2, 1):
            if len(cluster) >= size and cluster[-size:].lower() in _ONSETS:
                cut = j - size
                break
        cuts.append(cut)
    pieces, prev = [], 0
    for cut in cuts:
        pieces.append(unicodedata.normalize("NFC", decomp[prev:cut]))
        prev = cut
    pieces.append(unicodedata.normalize("NFC", decomp[prev:]))
    return [p for p in pieces if p]


_LETTER_RUN = re.compile(r"[^\W\d_]+", re.UNICODE)


def _pinyin_mark_to_number(text: str) -> str:
    def _convert_run(m: re.Match) -> str:
        out = []
        for syl in _split_run(m.group(0)):
            decomp = unicodedata.normalize("NFD", syl)
            tone = 5
            kept = []
            for c in decomp:
                if c in _COMBINING_TONE:
                    tone = _COMBINING_TONE[c]
                else:
                    kept.append(c)
            out.append(unicodedata.normalize("NFC", "".join(kept)) + str(tone))
        return "".join(out)
    return _LETTER_RUN.sub(_convert_run, text)


def _pinyin_strip(text: str) -> str:
    def _strip_run(m: re.Match) -> str:
        decomp = unicodedata.normalize("NFD", m.group(0))
        kept = "".join(c for c in decomp if c not in _COMBINING_TONE)
        return unicodedata.normalize("NFC", kept)
    # digits are removed only when attached to a letter (tone digits), so
    # ordinary numerals in surrounding text survive
    return re.sub(r"(?<=[^\W\d_])[0-5]", "", _LETTER_RUN.sub(_strip_run, text))


# ---------------------------------------------------------------------------
# Jamo form
# ---------------------------------------------------------------------------
# Conjoining→compatibility is a direct table.  Compatibility→conjoining needs
# position: compatibility jamo do not distinguish onset from coda (both ㄱ are
# U+3131), so a consonant is treated as an onset when a vowel follows,
# otherwise as a coda — deterministic over well-formed jamo sequences.

@functools.lru_cache(maxsize=1)
def _jamo_tables():
    from scriptconv.translit import _ONSETS as _CO, _VOWELS as _CV, _CODAS as _CT
    conj_to_compat = {}
    compat_onset = {}
    compat_vowel = {}
    compat_coda = {}
    for i, ch in enumerate(_CO):
        conj_to_compat[chr(0x1100 + i)] = ch
        compat_onset[ch] = chr(0x1100 + i)
    for i, ch in enumerate(_CV):
        conj_to_compat[chr(0x1161 + i)] = ch
        compat_vowel[ch] = chr(0x1161 + i)
    for i, ch in enumerate(_CT):
        if ch:
            conj_to_compat[chr(0x11A8 + i - 1)] = ch
            compat_coda[ch] = chr(0x11A8 + i - 1)
    return conj_to_compat, compat_onset, compat_vowel, compat_coda


def _jamo_conjoining_to_compat(text: str) -> str:
    table = _jamo_tables()[0]
    return "".join(table.get(c, c) for c in text)


def _jamo_compat_to_conjoining(text: str) -> str:
    _, onset, vowel, coda = _jamo_tables()
    out = []
    for i, c in enumerate(text):
        if c in vowel:
            out.append(vowel[c])
        elif c in onset or c in coda:
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if nxt in vowel and c in onset:
                out.append(onset[c])
            elif c in coda:
                out.append(coda[c])
            else:
                out.append(onset[c])
        else:
            out.append(c)
    return "".join(out)


def _jamo_detect(text: str) -> Optional[str]:
    for c in text:
        cp = ord(c)
        if 0x1100 <= cp <= 0x11FF:
            return "conjoining"
        if 0x3130 <= cp <= 0x318F:
            return "compatibility"
    return None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Tashkeel deliberately EXCLUDES U+0653–0655 (madda above, hamza above, hamza
# below): in NFD text آ/أ/إ decompose to alef + those marks, which are letter
# identity — stripping them would corrupt the consonantal skeleton.
_TASHKEEL_RANGES = ((0x064B, 0x0652), (0x0656, 0x065F), (0x0670, 0x0670),
                    (0x08F0, 0x08F2))
_KASHIDA_RANGES = ((0x0640, 0x0640),)
# 06DD/06DE (end of ayah, rub el hizb) are structural signs and 06E5/06E6 are
# small letters — kept; 06E7-06E9 (small high marks, place of sajdah) and
# 06EA-06ED are annotation marks — stripped.
_QURANIC_RANGES = ((0x06D6, 0x06DC), (0x06DF, 0x06E4), (0x06E7, 0x06ED))
# Niqqud includes dagesh/mapiq U+05BC, meteg U+05BD (a masoretic stress mark,
# but traditionally stripped with the points), rafe U+05BF and the shin/sin
# dots U+05C1/05C2 — stripping loses the שׁ/שׂ distinction, exactly as
# unpointed Hebrew does.  Maqaf U+05BE, sof pasuq U+05C3 and nun hafukha
# U+05C6 are punctuation and survive.
_NIQQUD_RANGES = ((0x05B0, 0x05BD), (0x05BF, 0x05BF), (0x05C1, 0x05C2),
                  (0x05C7, 0x05C7))
_TEAMIM_RANGES = ((0x0591, 0x05AF), (0x05C0, 0x05C0), (0x05C4, 0x05C5))


def _marks(id: str, name: str, scripts: Tuple[str, ...],
           ranges: Tuple[Tuple[int, int], ...], reference: str,
           *, default: str = "marked") -> Convention:
    """A binary decoration: strippable marks with a range-based detector."""
    return Convention(id, name, scripts, None, ("marked", "none"), default,
                      ranges, reference,
                      transitions=(Transition("marked", "none", _range_strip(ranges)),),
                      detector=_range_detector(ranges))


CONVENTION_REGISTRY: Dict[str, Convention] = {c.id: c for c in (
    _marks("tashkeel", "Arabic vocalization (harakat/tanwin/shadda/sukun)",
           ("Arab",), _TASHKEEL_RANGES,
           "Unicode 15 ch. 9.2 (Arabic); excludes letter-identity U+0653-0655"),
    _marks("kashida", "Arabic justification elongation (tatweel)",
           ("Arab",), _KASHIDA_RANGES, "Unicode U+0640 ARABIC TATWEEL",
           default="none"),
    _marks("quranic-marks", "Quranic annotation signs",
           ("Arab",), _QURANIC_RANGES,
           "Unicode U+06D6-06ED Quranic annotation signs", default="none"),
    _marks("niqqud", "Hebrew vocalization points",
           ("Hebr",), _NIQQUD_RANGES,
           "Unicode 15 ch. 9.1 (Hebrew); strip loses the shin/sin dot distinction"),
    _marks("teamim", "Hebrew cantillation marks",
           ("Hebr",), _TEAMIM_RANGES,
           "Unicode U+0591-05AF Hebrew accents (masoretic)", default="none"),
    Convention("wakachigaki", "Japanese spaced writing (分かち書き)",
               ("Hira", "Kana", "Hani"), "japanese", ("marked", "none"), "none",
               (), "Spaced orthographic mode of Japanese (children's books, games)",
               transitions=(
                   Transition("marked", "none", _wakachigaki_strip),
                   Transition("none", "marked", _wakachigaki_apply, requires="ja"),
               )),
    Convention("pinyin-tone", "Pinyin tone spelling",
               ("Latn",), "pinyin", ("mark", "number", "none"), "mark",
               (), "GB/T 16159 Basic rules of Hanyu Pinyin orthography",
               transitions=(
                   Transition("mark", "number", _pinyin_mark_to_number),
                   Transition("number", "mark", _pinyin_number_to_mark),
                   Transition("mark", "none", _pinyin_strip),
                   Transition("number", "none", _pinyin_strip),
               )),
    Convention("jamo-form", "Hangul jamo repertoire (compatibility vs conjoining)",
               ("Hang",), None, ("compatibility", "conjoining"), "compatibility",
               (), "Unicode Hangul Compatibility Jamo U+3130 vs Hangul Jamo U+1100",
               transitions=(
                   Transition("conjoining", "compatibility",
                              _jamo_conjoining_to_compat, lossless=True),
                   Transition("compatibility", "conjoining",
                              _jamo_compat_to_conjoining, lossless=True),
               ),
               detector=_jamo_detect),
)}


def conventions_for(script: str) -> List[Convention]:
    """Conventions that decorate *script* (ISO-15924 code), registry order."""
    return [c for c in CONVENTION_REGISTRY.values() if script in c.scripts]


def _conv(convention_id: str) -> Convention:
    try:
        return CONVENTION_REGISTRY[convention_id]
    except KeyError:
        raise ValueError(
            f"unknown convention {convention_id!r}; known: "
            f"{', '.join(sorted(CONVENTION_REGISTRY))}") from None


# Module-level facades over the conventions' own behavior — the published API.

def restyle(text: str, convention_id: str, to: str,
            frm: Optional[str] = None) -> str:
    """Rewrite *text* from one style of a convention to another."""
    return _conv(convention_id).restyle(text, to, frm=frm)


def strip(text: str, convention_id: str) -> str:
    """Remove a convention's decoration (restyle to ``"none"``)."""
    return _conv(convention_id).strip(text)


def apply(text: str, convention_id: str, style: Optional[str] = None) -> str:
    """Add a convention's decoration to unmarked text (restyle from ``"none"``)."""
    return _conv(convention_id).apply(text, style)


def detect(text: str, convention_id: str) -> Optional[str]:
    """Current style of *text* under a convention, or None when not character-evident."""
    return _conv(convention_id).detect(text)
