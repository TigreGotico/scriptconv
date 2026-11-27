<div align="center">

# scriptconv

**Every way text is written, and every path between them.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Build Tests](https://github.com/TigreGotico/scriptconv/actions/workflows/build-tests.yml/badge.svg?branch=dev)](https://github.com/TigreGotico/scriptconv/actions/workflows/build-tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/scriptconv.svg)](https://pypi.org/project/scriptconv/)

</div>

<!-- agent-hint
covers: what scriptconv does, the quickstart, and the documentation pages
source: `__all__` in scriptconv/__init__.py, scriptconv/phonemizers/registry.py, scriptconv/phonemizers/_moved.py, pyproject.toml
generated: no
verify: python scripts/check_doc_page.py README.md
see: docs/index.md, docs/stack.md, docs/reference.md, AGENTS.md
-->

scriptconv tells you which representation a text is in, converts it to
another representation, and phonemizes it. It covers scripts (Cyrillic,
Hangul, kana), romanizations (pinyin, Buckwalter), phoneme notations (IPA,
ARPABET, X-SAMPA), input codes (Cangjie) and decorated spellings (Arabic with
or without vowel marks). Each conversion reports how faithful it is, as data
that code can read.

The core is pure Python with no dependencies. The `phonemizers` subpackage
gives one interface to many grapheme-to-phoneme backends: espeak, gruut,
orthography2ipa, tugaphone, arbtok and more, each behind an optional extra.
`TextFrontend` joins the text stages and a backend in one fixed order for a
voice.

## Quickstart

```bash
uv pip install --prerelease=allow "scriptconv[pt-phonemizers]"
```

```python
from scriptconv import detect_script, convert, strip
from scriptconv.phonemizers import phonemize

detect_script("Здравствуйте")             # 'Cyrl'
convert("HH AH0 L OW1", "arpa", "ipa")    # 'həloʊ'
strip("مُحَمَّد", "tashkeel")               # 'محمد'
phonemize("Olá mundo", "pt")              # 'ɔˈla ˈmũdu'
```

The first three calls need no extra. The last one needs the extra of its
backend, here `pt-phonemizers` for tugaphone. Every call is also a command
of `python -m scriptconv` ([docs/graph.md](docs/graph.md#cli)).

## Documentation

| Page | Read it for |
| --- | --- |
| [docs/overview.md](docs/overview.md) | the model, a tour of each module, related projects |
| [docs/stack.md](docs/stack.md) | where scriptconv sits in the speech stack, and which library runs each stage |
| [docs/install.md](docs/install.md) | the extras and the licences |
| [docs/backends.md](docs/backends.md) | every phonemizer backend and its extra |
| [docs/reference.md](docs/reference.md) | the signature of each public name |
| [docs/index.md](docs/index.md) | every page in reading order |
| [AGENTS.md](AGENTS.md) | the contributor rules |
