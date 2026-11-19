"""Dizione: English text to phonemes.

A dictionary built from CMUdict, a small model for words the dictionary
lacks, homograph rules, and text rules for numbers, dates, money, units and
chat forms. See ``docs/design.md``.

    import dizione
    print(dizione.phonemize("Hello, it costs $3.50."))
"""

import hashlib
import json
from pathlib import Path

from .symbols import Phonemized, tokenize

__version__ = "0.1.0"
VERSION = 4          # token-convention version recorded by models trained on the output
_BUILT = ("lexicon.tsv", "align.json", "g2p.json", "g2p.npz", "homographs.json")
_default = None


def get():
    """The phonemizer over the default data directory, loaded once."""
    global _default
    if _default is None:
        from .engine import Phonemizer
        _default = Phonemizer()
    return _default


def reset():
    """Forget the loaded phonemizer (after the data directory or the tables changed)."""
    global _default
    _default = None


def pieces(text):
    """``(True, mark)`` for punctuation and ``(False, words)`` for text, in order."""
    return get().pieces(text)


def phonemize(text):
    """Text -> ``Phonemized`` (symbols, ids, stress)."""
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must not be empty")
    return tokenize(pieces(text))


def identity(directory=None):
    """Exactly which build produces the tokens: version, built files, tables
    and code. Record the fingerprint next to anything derived from the output,
    so tokens from two builds are never mixed."""
    from .engine import default_directory
    from .tables import DATA
    directory = Path(directory) if directory else default_directory()
    built = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest() for name in _BUILT if (directory / name).exists()}
    tables = hashlib.sha256()
    for path in sorted(DATA.glob("*.txt")):
        tables.update(path.name.encode())
        tables.update(path.read_bytes())
    code = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        code.update(path.name.encode())
        code.update(path.read_bytes())
    parts = {"version": VERSION, "built": built, "tables": tables.hexdigest(), "code": code.hexdigest()}
    fingerprint = hashlib.sha256(json.dumps(parts, sort_keys=True).encode()).hexdigest()
    return {**parts, "fingerprint": fingerprint}


__all__ = ["Phonemized", "phonemize", "pieces", "identity", "get", "reset", "tokenize", "VERSION"]
