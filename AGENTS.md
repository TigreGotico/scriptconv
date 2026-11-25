# AGENTS.md

scriptconv detects the writing system of a text, converts between scripts and
phoneme notations, and phonemizes text through one registry of backends. The
core has no dependencies, and each phonemizer engine sits behind an extra.

## Map

| Path | Holds |
|---|---|
| `scriptconv/scripts.py`, `notation.py`, `translit.py`, `cangjie.py`, `readings.py`, `conventions.py`, `graph.py` | The core modules, one docs page each |
| `scriptconv/diacritics.py` | `diacritize` and `strip_diacritics`, and the diacritics graph edges |
| `scriptconv/frontend.py` | `TextFrontend`, the stage order for a voice |
| `scriptconv/phonemizers/enums.py` | The `Phonemizer` and `Alphabet` enums |
| `scriptconv/phonemizers/registry.py` | `PHONEMIZER_REGISTRY`, `LANG_DEFAULTS`, `get_phonemizer` |
| `scriptconv/phonemizers/_moved.py` | The wrappers that live in scriptconv-copyleft and scriptconv-nonfree |
| `scriptconv/phonemizers/_thirdparty/`, `_vendored/` | Vendored engines, each with its licence notice |
| `scripts/` | The licence check, the backend table generator, the docs page check, the figure generator `docs_figures.py` and measurement scripts |
| `examples/` | Runnable examples, run by `tests/test_examples.py` |
| `docs/` | The documentation. [docs/index.md](docs/index.md) gives the reading order |

## Setup and tests

```bash
uv venv
uv pip install --prerelease=allow -e '.[test]'
pytest tests/
```

CI runs the same suite on Python 3.11, 3.12 and 3.13 with `espeak-ng`
installed (`.github/workflows/build-tests.yml`).

## Rules that the code, the tests or the docs enforce

- The core imports no third-party module. `tests/test_core_imports.py` fails
  otherwise, and `pyproject.toml` keeps `dependencies = []`.
- A `Phonemizer` value is wire format, because voice configs store it. Never
  rename one. See [docs/phonemizers.md](docs/phonemizers.md).
- A backend imports its engine lazily. A missing engine raises an
  `ImportError` that names the extra
  (`tests/test_phonemizers_friendly_import_errors.py`).
- [docs/backends.md](docs/backends.md) holds one row per `Phonemizer`
  member, in enum order. `python scripts/backend_table.py --write` writes the
  rows, and `tests/test_backend_table.py` fails on a stale table.
- `docs/figures/*.svg` and the Mermaid diagram of `docs/graph.md` come from the registry,
  the graph and `scripts/time_owner_backends.txt`. `scripts/docs_figures.py --check` fails otherwise.
- The python examples of each page with an agent hint give the results that
  the page shows. `tests/test_doc_pages.py` fails otherwise.
- No extra installs a copyleft or non-commercial distribution, except the two
  that `scripts/check_extra_licences.py` lists. Such a wrapper goes to
  scriptconv-copyleft or scriptconv-nonfree. `tests/test_wheel_licences.py`
  checks the wheel. See the Licensing section of [README.md](README.md).
- scriptconv does not normalise text. Normalisation is the caller's hook. See
  [docs/stack.md](docs/stack.md).
- ByT5, Charsiu and phonetisaurus never download a model. See
  [docs/backends.md](docs/backends.md#model-files).
- A backend that hashes its code path reports a `revision`. A change to that
  code changes the revision. See [docs/phonemizers.md](docs/phonemizers.md).

## Before a push

```bash
pytest tests/
python scripts/check_extra_licences.py
python scripts/backend_table.py --check
python scripts/docs_figures.py --check          # the SVG figures and the graph diagram
python scripts/check_doc_page.py docs/stack.md   # once for each changed page
```

After a change to the code or to a page, run the `verify` command in the
agent hint of each page that the change touches. The hint is the HTML comment
under the title of the page. `scripts/check_doc_page.py` runs the examples of a
page, and its docstring lists what it checks. `tests/test_doc_pages.py` runs
it on each page that has a hint.

The build workflow runs on pull requests to `dev` and `master`. The two licence
workflows run on pull requests to `dev`.
