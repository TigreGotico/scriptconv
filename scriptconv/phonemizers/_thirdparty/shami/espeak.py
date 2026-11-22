"""Thin wrapper around the ``espeak-ng`` CLI for IPA phonemisation.

Ported from hams_tts.text.espeak (Apache-2.0).  Kept inside thirdparty/shami so the
vendored front-end is self-contained even on machines where a broader TTS
espeak phonemizer is unused.
"""

from __future__ import annotations

import functools
import re
import shutil
import subprocess

_ESPEAK = shutil.which("espeak-ng") or shutil.which("espeak")

_PAREN = re.compile(r"\([^)]*\)")
_ZW = dict.fromkeys(map(ord, "‍‌​﻿"), None)

# espeak-ng time grows with the text: about 150 microseconds per UTF-8 byte at
# load 35 on an 8-core laptop. The allowance is four times that rate, for a box
# at load 50 and above. The base bounds a binary that hangs on a short text.
_TIMEOUT_BASE = 30
_TIMEOUT_PER_BYTE = 4 * 150e-6


def available() -> bool:
    return _ESPEAK is not None


def binary() -> str | None:
    return _ESPEAK


@functools.lru_cache(maxsize=8192)
def phonemize(text: str, voice: str = "en-us") -> str:
    """Return a space-delimited IPA string (words separated by single spaces)."""
    if not _ESPEAK:
        raise RuntimeError("espeak-ng not found on PATH")
    if not text.strip():
        return ""
    # The text goes on stdin, because Linux refuses one argument longer than
    # 128 KiB. Without the final newline, espeak-ng drops the end of the last word.
    data = text + "\n"
    proc = subprocess.run(
        [_ESPEAK, "-v", voice, "--ipa=1", "-q", "--stdin"],
        input=data,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_TIMEOUT_BASE + _TIMEOUT_PER_BYTE * len(data.encode()),
    )
    raw = proc.stdout or ""
    raw = _PAREN.sub(" ", raw).translate(_ZW)
    words = []
    for w in raw.split():
        phon = w.replace("_", "").strip()
        if phon:
            words.append(phon)
    return " ".join(words)
