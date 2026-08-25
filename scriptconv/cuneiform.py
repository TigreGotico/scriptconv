"""Cuneiform signs and the sign names Unicode gives them.

Assyriology writes a cuneiform text twice: once in the signs themselves, and
once in a Latin transliteration that names each sign. The Unicode Standard
carries one of those names for every sign it encodes — ``U+12000`` is
``CUNEIFORM SIGN A``, ``U+1202D`` is ``CUNEIFORM SIGN AN`` — and those names
are the sign values the field writes in capitals: ``AN``, ``LUGAL``,
``AB TIMES ASH``.

That correspondence is this module's whole subject, and it is worth being
exact about what it is not. A sign has many readings. ``𒀭`` is read ``an``,
``dingir`` or ``il`` depending on the word it stands in, and choosing between
them is a question about the language, not about the writing system —
Akkadian, Sumerian and Hittite disagree about the same sign. Unicode's name
records the conventional sign *value* only, so that is what converts here.
Anything that needs a reading needs a lexicon and a language, and neither is
in scriptconv's scope.

What this buys is exact and reversible at the level of signs: every encoded
sign has exactly one Unicode name, no two signs share one, so a sign sequence
survives a round trip unchanged. Two things do not survive it. Spacing is not
carried — the sign names need separating from each other, and the signs do
not, so the two directions cannot agree on what a space meant. And a name
Unicode never assigned has no sign to become.

The table is not shipped. It is read out of :mod:`unicodedata` at import, so
it is the standard's own data rather than a copy of it that can drift, and it
follows whatever Unicode version the interpreter was built against.

Reference
---------
The Unicode Standard, "Cuneiform" (U+12000–U+123FF), "Cuneiform Numbers and
Punctuation" (U+12400–U+1247F), and "Early Dynastic Cuneiform"
(U+12480–U+1254F).
"""

from __future__ import annotations

import re
import sys
import unicodedata

__all__ = [
    "CUNEIFORM_BLOCKS",
    "readings_to_cuneiform",
    "sign_readings_table",
    "cuneiform_to_sign_names",
    "sign_names_to_cuneiform",
    "sign_name",
    "sign_for_name",
    "is_cuneiform",
]

#: The three blocks Unicode encodes cuneiform in, as inclusive ranges.
CUNEIFORM_BLOCKS: tuple[tuple[int, int], ...] = (
    (0x12000, 0x123FF),  # Cuneiform
    (0x12400, 0x1247F),  # Cuneiform Numbers and Punctuation
    (0x12480, 0x1254F),  # Early Dynastic Cuneiform
)

#: Unicode spells every one of these names with the same two prefixes.
_PREFIXES = ("CUNEIFORM SIGN ", "CUNEIFORM NUMERIC SIGN ",
             "CUNEIFORM PUNCTUATION SIGN ")


def _build() -> tuple[dict[str, str], dict[str, str]]:
    to_name: dict[str, str] = {}
    to_sign: dict[str, str] = {}
    for start, end in CUNEIFORM_BLOCKS:
        for codepoint in range(start, end + 1):
            char = chr(codepoint)
            try:
                full = unicodedata.name(char)
            except ValueError:
                # Unassigned in this interpreter's Unicode version. Newer
                # signs simply do not convert here rather than converting
                # wrongly.
                continue
            for prefix in _PREFIXES:
                if full.startswith(prefix):
                    name = full[len(prefix):]
                    break
            else:
                continue
            to_name[char] = name
            # Names are unique in Unicode, so this never overwrites.
            to_sign[name] = char
    return to_name, to_sign


_TO_NAME, _TO_SIGN = _build()

#: Longest first, so `AB TIMES ASH` is read whole rather than as `AB`.
_NAME_RE = re.compile("|".join(
    re.escape(name) for name in sorted(_TO_SIGN, key=len, reverse=True)))


def is_cuneiform(char: str) -> bool:
    """True when ``char`` is a cuneiform sign this module knows."""
    return char in _TO_NAME


def sign_name(sign: str) -> str | None:
    """The Unicode sign name for one sign, or ``None`` if it is not one."""
    return _TO_NAME.get(sign)


def sign_for_name(name: str) -> str | None:
    """The sign for one Unicode sign name, or ``None`` if there is none."""
    return _TO_SIGN.get(name.strip().upper())


def cuneiform_to_sign_names(text: str, errors: str = "pass",
                            separator: str = " ") -> str:
    """Replace each cuneiform sign with its Unicode sign name.

    Signs are joined with ``separator``; anything that is not a sign is
    resolved by the usual ``errors`` policy. Whitespace already in the input
    is dropped, because the sign names carry their own separation and keeping
    both would double it.
    """
    from scriptconv.notation import _unknown

    out: list[str] = []
    for position, char in enumerate(text):
        name = _TO_NAME.get(char)
        if name is not None:
            out.append(name)
        elif char.isspace():
            continue
        else:
            resolved = _unknown(char, position, "cuneiform", errors)
            if resolved:
                out.append(resolved)
    return separator.join(out)


def sign_names_to_cuneiform(text: str, errors: str = "pass",
                            separator: str = "") -> str:
    """Replace each Unicode cuneiform sign name with its sign.

    Names are matched longest first, so ``AB TIMES ASH`` is one sign rather
    than ``AB`` followed by unmatched text. Matching is case-insensitive
    because the field writes sign values in capitals and readers do not.
    """
    from scriptconv.notation import _unknown

    upper = text.upper()
    out: list[str] = []
    position = 0
    for match in _NAME_RE.finditer(upper):
        gap = upper[position:match.start()].strip()
        if gap:
            resolved = _unknown(text[position:match.start()].strip(),
                                position, "cuneiform-sign-names", errors)
            if resolved:
                out.append(resolved)
        out.append(_TO_SIGN[match.group()])
        position = match.end()
    tail = upper[position:].strip()
    if tail:
        resolved = _unknown(text[position:].strip(), position,
                            "cuneiform-sign-names", errors)
        if resolved:
            out.append(resolved)
    return separator.join(out)


# ---------------------------------------------------------------------------
# Readings, from the optional `cuneiscribe` table
# ---------------------------------------------------------------------------
#
# Everything above converts sign *values* — the names Unicode assigns. Actual
# Assyriological transliteration writes *readings*: `a-na`, `dan-nu`,
# `LUGAL`. Going from those to signs needs a reading list, which is a
# scholarly artifact rather than something derivable, and this library ships
# none.
#
# `cuneiscribe` publishes one: 14,240 readings over 1,779 sign sequences,
# bundled in its wheel. It is used here the way the phonemizer engines are —
# an optional install the caller opts into, read from wherever pip put it,
# never copied into this package. Nothing here redistributes it, so its terms
# stay its own.

_READINGS: Optional[dict[str, str]] = None

#: ATF marks a determinative — a silent classifier like `{d}` for a divine
#: name — in braces. It is not read aloud and has no sign of its own.
_DETERMINATIVE = re.compile(r"\{[^}]*\}")

#: Readings are separated by hyphens or dots inside a word.
_SYLLABLE = re.compile(r"[-.]")


def sign_readings_table() -> dict[str, str]:
    """The reading-to-signs table from an installed ``cuneiscribe``.

    Located rather than imported. ``cuneiscribe``'s top-level package pulls
    in torch and transformers on import, and none of that is wanted to read a
    JSON file, so the package is found without being executed and its data
    file is read from disk.
    """
    global _READINGS
    if _READINGS is not None:
        return _READINGS

    import importlib.util
    import json
    from pathlib import Path

    spec = importlib.util.find_spec("cuneiscribe")
    if spec is None or not spec.submodule_search_locations:
        raise ImportError(
            "converting Assyriological readings to signs needs a reading "
            "list, which scriptconv does not ship. Install it: "
            "pip install 'scriptconv[cuneiscribe]'")
    path = (Path(spec.submodule_search_locations[0])
            / "knowledge" / "transliteration_mapping.json")
    if not path.exists():
        raise ImportError(
            f"cuneiscribe is installed but its sign table is not at {path}; "
            f"this is the file scriptconv reads readings from")
    _READINGS = json.loads(path.read_text(encoding="utf-8"))["transliteration_to_unicode"]
    return _READINGS


def readings_to_cuneiform(text: str, errors: str = "pass") -> str:
    """Convert Assyriological transliteration to cuneiform signs.

    Readings are separated by hyphens or dots within a word, words by spaces,
    and the sign sequence for each word is written without separators, which
    is the convention the table is built for::

        readings_to_cuneiform("a-na")     # '𒀀𒈾'
        readings_to_cuneiform("dan-nu")   # '𒆗𒉡'

    Determinatives are dropped. `{d}` before a divine name is a silent
    classifier: it is not pronounced and has no sign of its own.

    Case is tried exactly first and then lowered, because the field writes
    logograms in capitals (`LUGAL`) and syllables in lower case, and the
    table carries both.

    A reading the table does not have follows the usual ``errors`` policy. It
    is deliberately **not** guessed at: `cuneiscribe`'s own lookup falls back
    to stripping subscripts, so an unknown `u₂` becomes the sign for `u` —
    a different sign, returned silently. An index digit is part of a
    reading's identity, not decoration on it.

    This direction only. A sign sequence has many readings — 1505 of the
    1779 in the table do — so the reverse is a question about the language,
    and :func:`cuneiform_to_sign_names` is the reverse that has one answer.
    """
    from scriptconv.notation import _unknown

    table = sign_readings_table()
    out: list[str] = []
    for word in _DETERMINATIVE.sub("", text).split():
        signs: list[str] = []
        for position, syllable in enumerate(_SYLLABLE.split(word)):
            if not syllable:
                continue
            sign = table.get(syllable) or table.get(syllable.lower())
            if sign is None:
                resolved = _unknown(syllable, position, "sign-readings", errors)
                if resolved:
                    signs.append(resolved)
            else:
                signs.append(sign)
        if signs:
            out.append("".join(signs))
    return " ".join(out)
