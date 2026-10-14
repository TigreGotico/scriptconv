# Using scriptconv from OVOS: `ovos-scriptconv-g2p-plugin`

[ovos-scriptconv-g2p-plugin](https://github.com/TigreGotico/ovos-scriptconv-g2p-plugin)
is an [OVOS Plugin Manager](https://github.com/OpenVoiceOS/ovos-plugin-manager)
(OPM) `opm.g2p` plugin. It implements no phonemization itself, it is a thin
adapter that exposes `scriptconv.phonemizers` through OVOS's
`Grapheme2PhonemePlugin` contract, so any OVOS component that asks for G2P
through OPM gets scriptconv's full backend catalog and per-language
[fallback chain](phonemizers.md#the-registry-and-per-language-defaults) for
free.

## Install

```bash
pip install ovos-scriptconv-g2p-plugin
```

Published on PyPI. Its only hard dependencies are `scriptconv` and
`ovos-plugin-manager`; the 45 individual phonemizer backends stay optional —
scriptconv lazy-imports them, and the plugin does not pull any of them in.
Configuring a backend whose package isn't installed raises an `ImportError`
naming the pip extra to add, e.g. `pip install scriptconv[espeak]`.

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

- `phonemizer` (optional) — registry name of the `Phonemizer` to use
  (`"espeak"`, `"orthography2ipa"`, `"tugaphone"`, ...). Omit it to let
  scriptconv's own `LANG_DEFAULTS` fallback chain pick a backend per
  language, exactly as calling `scriptconv.phonemizers.phonemize()` directly
  would.
- `lang` (optional) — default language used when a caller doesn't pass one
  explicitly.
- any other key is forwarded as a keyword argument to the underlying
  phonemizer's constructor (`model`, `normalizer`, ...).

A second example, letting scriptconv pick the backend for Portuguese
(resolves to `tugaphone` per `LANG_DEFAULTS`):

```json
"g2p": {
    "module": "ovos-scriptconv-g2p-plugin",
    "ovos-scriptconv-g2p-plugin": {
        "lang": "pt"
    }
}
```

## How backend selection works

`get_ipa()` always requests `Alphabet.IPA` from scriptconv, so callers get
IPA back regardless of which backend is configured, including backends that
natively emit ARPABET, X-SAMPA, or another notation — scriptconv's own
[notation transcoding](notation.md) handles the conversion before the result
reaches OVOS. With no `phonemizer` set, resolution follows scriptconv's
ordinary per-language chain: an explicit language default first, then
`orthography2ipa` wherever it has a spec for the language, then espeak as
the universal fallback (Arabic is the one exception — it never falls back
past `arbtok`).

## Links

- [ovos-scriptconv-g2p-plugin](https://github.com/TigreGotico/ovos-scriptconv-g2p-plugin) —
  the plugin itself
- [phonemizers.md](phonemizers.md) — the scriptconv layer this plugin wraps
- [ovos-plugin-arena](https://github.com/TigreGotico/ovos-plugin-arena) —
  benchmarks this plugin against other OVOS G2P engines

---
[← phonemizers](phonemizers.md) · [Home](../README.md)
