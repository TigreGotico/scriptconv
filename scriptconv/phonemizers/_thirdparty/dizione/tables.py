"""Hand-written tables that ship with the source (``data/*.txt``).

Plain text, one entry per line, columns separated by tabs or by two or more
spaces, ``#`` starts a comment line. Pronunciations are either phones of the
TTS inventory with stress marks (``h ə l ˈoʊ``) or CMUdict notation
(``HH AH0 L OW1``); the reader tells them apart.
"""

from pathlib import Path
import re

from .convert import from_text, is_arpabet

DATA = Path(__file__).parent / "data"
_COLUMNS = re.compile(r"\t+| {2,}")
STRESS_CLASSES = frozenset(("u", "uf", "ur", "s", "ss", "si", "pf", "p"))


def rows(source):
    """Rows of a table given as a file name in ``data/``, a path or a text."""
    if isinstance(source, Path):
        text = source.read_text(encoding="utf-8")
    elif "\n" in source or "  " in source or "\t" in source:
        text = source
    else:
        text = (DATA / source).read_text(encoding="utf-8")
    for number, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if line and not line.startswith("#"):
            yield number, [column.strip() for column in _COLUMNS.split(line)]


def function_words():
    """word -> (class, form, final form or None)."""
    table = {}
    for number, columns in rows("function_words.txt"):
        if len(columns) not in (3, 4) or columns[1] not in STRESS_CLASSES:
            raise ValueError(f"function_words.txt line {number}: expected word, class, form[, final form]")
        table[columns[0]] = (columns[1], from_text(columns[2]), from_text(columns[3]) if len(columns) == 4 else None)
    return table


def phrases():
    """(word, word, ...) -> (class, forms, final form or None). ``forms`` has one
    entry per spoken word of the group: a single one when the words are joined,
    several when the form is written with ``|`` and the boundaries stay."""
    table = {}
    for number, columns in rows("phrases.txt"):
        if len(columns) not in (3, 4) or columns[1] not in STRESS_CLASSES:
            raise ValueError(f"phrases.txt line {number}: expected words, class, form[, final form]")
        forms = tuple(from_text(part) for part in columns[2].split("|"))
        if len(forms) > 1 and (columns[1] != "p" or len(forms) != len(columns[0].split())):
            raise ValueError(f"phrases.txt line {number}: a form with boundaries needs class p and one part per word")
        table[tuple(columns[0].split())] = (columns[1], forms, from_text(columns[3]) if len(columns) == 4 else None)
    return table


def _entries(source):
    if isinstance(source, dict):
        return [(word, [word, pronunciation]) for word, pronunciation in source.items()]
    return list(rows(source))


def _pronunciation(text):
    symbols = text.split()
    return ("arpabet", symbols) if is_arpabet(symbols) else ("phones", from_text(text))


def pronunciations(source):
    """word -> ("arpabet", [symbols]) or ("phones", ((phone, stress), ...)).

    Used for the built-in exception list and for user override files. Rows
    whose first column has several words are names: see ``names``."""
    table = {}
    for where, columns in _entries(source):
        if len(columns) != 2:
            raise ValueError(f"{where}: expected a word and its pronunciation, separated by a tab or two spaces")
        if len(columns[0].split()) == 1:
            table[columns[0].lower()] = _pronunciation(columns[1])
    return table


def names(source):
    """(word, word, ...) -> one pronunciation per word, for a name of several
    words whose rhythm matters: ``tung tung tung sahur`` with
    ``T UW1 NG | T UW2 NG | T UW2 NG | S AA0 HH UH1 R``. The pronunciations
    are separated by ``|``; the stress written is the stress spoken."""
    table = {}
    for where, columns in _entries(source):
        words = columns[0].lower().split()
        if len(columns) != 2 or len(words) < 2:
            continue
        parts = [part.strip() for part in columns[1].split("|")]
        if len(parts) != len(words):
            raise ValueError(f"{where}: {columns[0]!r} has {len(words)} words and {len(parts)} pronunciations; "
                             "write one per word, separated by |")
        table[tuple(words)] = tuple(_pronunciation(part) for part in parts)
    return table


def mapping(name):
    """Two-column table as a dictionary (second column may be empty)."""
    return {columns[0]: (columns[1] if len(columns) > 1 else "") for _, columns in rows(name)}
