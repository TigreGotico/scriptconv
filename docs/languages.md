# Leader languages

<!-- agent-hint
covers: the default phonemizer backend, its extra and the script of each leader language
source: LANG_DEFAULTS and PHONEMIZER_REGISTRY in scriptconv/phonemizers/registry.py, lang_to_script in scriptconv/scripts.py, through scripts/backend_table.py
generated: yes for the table between the languages markers, by scripts/backend_table.py. Edit the registry and run the script, not the output
verify: python scripts/backend_table.py --check && python scripts/check_doc_page.py docs/languages.md
see: docs/backends.md, docs/phonemizers.md, docs/scripts.md
-->

This page tells what scriptconv does for each leader language.
`phonemizer_for_lang` selects the backend. It uses the language subtag only,
so `pt-PT` and `pt-BR` get the same backend.

- **Default backend**: the `LANG_DEFAULTS` chain of the language. The first
  backend in the chain that emits the requested alphabet wins.
- **none**: the language has no `LANG_DEFAULTS` entry. The code uses
  `orthography2ipa` when that package is installed and has a spec for the
  language. Otherwise it uses `espeak`.
- **Extra**: the extra of `scriptconv` that installs each backend in the row.
- **Script**: the ISO 15924 code that `lang_to_script` returns. "not in the
  map" means that `lang_to_script` returns `None`.
- **Measured score**: this repo holds no phoneme error rate for a language.
  The scores of each backend are in the repo of that backend.

<!-- languages:start -->
| Language | Default backend | Extra | Script | Measured score |
|---|---|---|---|---|
| `pt-PT` | `tugaphone` | `pt-phonemizers` | `Latn` | no score in this repo |
| `pt-BR` | `tugaphone` | `pt-phonemizers` | `Latn` | no score in this repo |
| `es-CO` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | `Latn` | no score in this repo |
| `fr-FR` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | `Latn` | no score in this repo |
| `it-IT` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | `Latn` | no score in this repo |
| `de-DE` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | `Latn` | no score in this repo |
| `nl-NL` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | `Latn` | no score in this repo |
| `da-DK` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | `Latn` | no score in this repo |
| `kab` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | not in the map | no score in this repo |
| `hi-IN` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | `Deva` | no score in this repo |
| `bn-IN` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | `Beng` | no score in this repo |
| `mwr` | none: `orthography2ipa` when it has a spec, else `espeak` | `o2i`, `espeak` | not in the map | no score in this repo |
<!-- languages:end -->

Run `python scripts/backend_table.py --write` to write the table again after
a change to the registry.

---
[← Prev](backends.md) · [Home](index.md) · [Next →](performance.md)
