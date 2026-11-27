# Using scriptconv from OVOS: `ovos-scriptconv-g2p-plugin`

<!-- agent-hint
covers: the OVOS G2P plugin, its config keys and how it picks a backend
source: `ScriptconvG2PPlugin` and `_RESERVED_KEYS` in ovos_scriptconv_g2p_plugin/__init__.py of TigreGotico/ovos-scriptconv-g2p-plugin for the plugin, scriptconv/phonemizers/registry.py for the scriptconv calls
generated: no
verify: python scripts/check_doc_page.py docs/ovos.md
see: docs/backends.md, docs/phonemizers.md
-->

[ovos-scriptconv-g2p-plugin](https://github.com/TigreGotico/ovos-scriptconv-g2p-plugin)
is an [OVOS Plugin Manager](https://github.com/OpenVoiceOS/ovos-plugin-manager)
(OPM) `opm.g2p` plugin. It holds no grapheme-to-phoneme logic. It gives
`scriptconv.phonemizers` to OVOS through the `Grapheme2PhonemePlugin`
contract, so an OVOS component that asks OPM for G2P gets every scriptconv
backend and the per-language
[default chain](phonemizers.md#the-registry-and-per-language-defaults).

## Install

```bash
uv pip install --prerelease=allow ovos-scriptconv-g2p-plugin "scriptconv[espeak]"
```

The plugin depends on `scriptconv` and `ovos-plugin-manager` only. Install the
scriptconv extra of each backend you configure:
[docs/backends.md](backends.md) names them. A backend whose package is
missing raises an `ImportError` that names the extra.

## Configuration

```json
"g2p": {
    "module": "ovos-scriptconv-g2p-plugin",
    "ovos-scriptconv-g2p-plugin": {
        "phonemizer": "espeak",
        "lang": "en-us"
    }
}
```

The plugin reads these keys:

| Key | Default | Meaning |
|---|---|---|
| `phonemizer` | none | The `Phonemizer` value of the backend, such as `"espeak"`, `"orthography2ipa"` or `"tugaphone"`. Without it, the scriptconv default chain picks a backend per language, as `scriptconv.phonemizers.phonemize()` does |
| `lang` | `"en-us"` | The language for a call that does not pass one |
| `module` | | OPM writes this key into each plugin config. The plugin drops it |
| any other key | | A keyword argument for the backend constructor, such as `model` |

Without `phonemizer`, scriptconv picks the backend. For Portuguese it picks
`tugaphone`, the `pt` entry of `LANG_DEFAULTS`, which needs the
`pt-phonemizers` extra:

```json
"g2p": {
    "module": "ovos-scriptconv-g2p-plugin",
    "ovos-scriptconv-g2p-plugin": {
        "lang": "pt"
    }
}
```

## How backend selection works

`get_ipa()` asks scriptconv for `Alphabet.IPA`. The plugin does not transcode,
so set `phonemizer` only to a backend that emits IPA. A backend that emits its
own notation, such as `vosk`, raises a `ValueError`, and the plugin reports
`OutOfVocabulary`.

With no `phonemizer` set, scriptconv picks the backend per language. An
explicit language default comes first, then `orthography2ipa` for each
language it has a spec for, then espeak. Arabic never falls back past
`arbtok`.

The plugin passes each word to `scriptconv.phonemizers.phonemize`. These
calls show the scriptconv behaviour that the plugin relies on:

```python
from scriptconv.phonemizers import Alphabet, LANG_DEFAULTS, Phonemizer, phonemize, phonemizer_for_lang

[p.value for p in LANG_DEFAULTS["pt"]]   # ['tugaphone']
phonemize("привет", "ru", alphabet=Alphabet.IPA, override=Phonemizer.VOSK)   # ValueError: VoskPhonemizer emits the vosk-tts phoneme inventory, not 'ipa'
phonemizer_for_lang("ar", Alphabet.XSAMPA)   # ValueError: no eligible phonemizer for 'ar'
```

The plugin turns a `ValueError` or a `KeyError` from scriptconv into
`OutOfVocabulary`, or into `None` when the caller sets `ignore_oov`. It
raises an `ImportError` unchanged.

## Links

- [ovos-scriptconv-g2p-plugin](https://github.com/TigreGotico/ovos-scriptconv-g2p-plugin):
  the plugin.
- [phonemizers.md](phonemizers.md): the scriptconv layer that the plugin
  wraps.
- [ovos-plugin-arena](https://github.com/TigreGotico/ovos-plugin-arena):
  scores this plugin against other OVOS G2P engines.

---
[← Prev](frontend.md) · [Home](index.md) · [Next →](backends.md)
