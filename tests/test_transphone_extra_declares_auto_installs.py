"""The ``transphone`` extra installs every package that transphone would
otherwise install with pip during a call.

transphone 1.5.3 calls ``import_with_auto_install``, which runs
``pip.main(['install', name])`` when an import fails:

- ``transphone/lang/cmn/tokenizer.py:18-19``: ``jieba`` and ``pypinyin``
- ``transphone/lang/jpn/tokenizer.py:20-21``: ``mecab-python3`` and ``unidic-lite``
- ``transphone/lang/eng/tokenizer.py:17`` and ``phonepiece/lexicon.py:33``: ``cmudict``

transphone declares ``mecab-python3`` and ``cmudict`` itself, so the extra
must declare the other three.
"""
import re
from pathlib import Path

import tomllib

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"


def test_transphone_extra_declares_what_transphone_would_pip_install():
    extra = tomllib.loads(PYPROJECT.read_text())["project"]["optional-dependencies"]["transphone"]
    names = {re.match(r"[A-Za-z0-9_.-]+", req).group(0).lower() for req in extra}
    assert {"jieba", "pypinyin", "unidic-lite"} <= names
