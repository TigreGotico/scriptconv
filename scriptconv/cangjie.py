"""Hanzi → Cangjie input codes (fifth generation, traditional table).

Cangjie codes encode a glyph's SHAPE — its decomposition into geometric
radicals — not its reading: 日 is ``a`` because of what it looks like, however
it is pronounced.  That makes this a deterministic, table-driven orthographic
transcode like the rest of scriptconv's core: no reading dictionary, no
ambiguity, no phonology.

The table is vendored (gzipped, loaded lazily on first use) from the Cangjie5
project — https://github.com/Jackchows/Cangjie5, MIT License — so no runtime
download or extra dependency is needed.  Where the upstream table lists
alternative codes for a glyph, the primary (first) code is kept.
"""
from __future__ import annotations

import gzip
from importlib.resources import files
from typing import Dict, Optional

__all__ = ["cangjie_code", "to_cangjie"]

_TABLE: Optional[Dict[str, str]] = None


def _table() -> Dict[str, str]:
    global _TABLE
    if _TABLE is None:
        _TABLE = {}
        raw = files("scriptconv.data").joinpath("cangjie5_tc.tsv.gz").read_bytes()
        for line in gzip.decompress(raw).decode("utf-8").splitlines():
            if line.startswith("#"):
                continue
            ch, _, code = line.partition("\t")
            _TABLE[ch] = code
    return _TABLE


def cangjie_code(char: str) -> Optional[str]:
    """Return the Cangjie5 code for a single glyph, or None if unmapped."""
    return _table().get(char)


def to_cangjie(text: str, sep: str = " ") -> str:
    """Transcode hanzi in *text* to their Cangjie5 codes.

    Mapped glyphs become their code, joined by *sep*; runs of unmapped
    characters (Latin, digits, punctuation, rare glyphs) pass through
    unchanged as single tokens.
    """
    table = _table()
    tokens = []
    last_raw = False
    for ch in text:
        code = table.get(ch)
        if code is not None:
            tokens.append(code)
            last_raw = False
        elif last_raw:
            tokens[-1] += ch
        else:
            tokens.append(ch)
            last_raw = True
    return sep.join(tokens)
