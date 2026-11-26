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
so `pt-PT` and `pt-BR` get the same backend. The table is for the IPA
alphabet. For other alphabets, the code skips orthography2ipa: when the
`LANG_DEFAULTS` chain has no backend for the alphabet, it uses `espeak`.

- **Default backend**: the backend that `phonemizer_for_lang` returns with
  all extras installed. It is the `LANG_DEFAULTS` chain of the language when
  there is one. Otherwise it is `orthography2ipa` when that package has a
  spec for the language, else `espeak`.
- **unsupported**: the selected backend returns no phonemes for a word of
  the language.
- **Extra**: the extra of `scriptconv` that installs the backend.
- **Script**: the ISO 15924 code that `lang_to_script` returns. "not in the
  map" means that `lang_to_script` returns `None`.
- **Measured score**: a link to the scores of the backend, or "none" when no
  published score is known.

espeak-ng has no voice for `kab` or `mwr`.

<!-- languages:start -->
| Language | Default backend | Extra | Script | Measured score |
|---|---|---|---|---|
| `pt-PT` | `tugaphone` | `pt-phonemizers` | `Latn` | [tugaphone scoreboard](https://github.com/TigreGotico/tugaphone/blob/dev/docs/scoreboard.md) |
| `pt-BR` | `tugaphone` | `pt-phonemizers` | `Latn` | [tugaphone scoreboard](https://github.com/TigreGotico/tugaphone/blob/dev/docs/scoreboard.md) |
| `es-CO` | `orthography2ipa` | `o2i` | `Latn` | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `fr-FR` | `orthography2ipa` | `o2i` | `Latn` | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `it-IT` | `orthography2ipa` | `o2i` | `Latn` | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `de-DE` | `orthography2ipa` | `o2i` | `Latn` | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `nl-NL` | `orthography2ipa` | `o2i` | `Latn` | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `da-DK` | `orthography2ipa` | `o2i` | `Latn` | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `kab` | `orthography2ipa` | `o2i` | not in the map ([#494](https://github.com/TigreGotico/scriptconv/issues/494)) | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `hi-IN` | `orthography2ipa` | `o2i` | `Deva` | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `bn-IN` | `orthography2ipa` | `o2i` | `Beng` | [o2i scoreboard](https://github.com/TigreGotico/orthography2ipa/blob/dev/docs/evaluation/generated/scoreboard.md) |
| `mwr` | unsupported: `orthography2ipa` returns no phonemes | `o2i` | not in the map ([#494](https://github.com/TigreGotico/scriptconv/issues/494)) | none |
<!-- languages:end -->

Run `python scripts/backend_table.py --write` to write the table again after
a change to the registry.

---
[← Prev](backends.md) · [Home](index.md) · [Next →](performance.md)
