# Phonemizer backends

<!-- agent-hint
covers: every phonemizer backend, its class, its extra and its package, and the models that download
source: the Phonemizer enum in scriptconv/phonemizers/enums.py, PHONEMIZER_REGISTRY and LANG_DEFAULTS in scriptconv/phonemizers/registry.py
generated: no. The table rows follow the order of the Phonemizer enum, one row per member
verify: the second command under "List the backends" prints the value, class and extra of each row, in table order
see: docs/phonemizers.md, docs/stack.md
-->

Each backend is a member of the `Phonemizer` enum. Its string value is wire
format: voice configuration files store it, so it never changes. The registry
maps each member to a class and to the extra that installs its engine.

## List the backends

The registry holds the list. This command prints the value of each backend:

```bash
python -c "from scriptconv.phonemizers import Phonemizer; print(' '.join(p.value for p in Phonemizer))"
```

This command prints the value, class and extra of each backend, in the order
of the table below. Compare its output with the table to check the table:

```bash
python -c "from scriptconv.phonemizers import Phonemizer, PHONEMIZER_REGISTRY as R; [print(p.value, R[p][1], R[p][2] or 'phonemizers') for p in Phonemizer]"
```

## The table

The Extra column names the extra to install. Each phonemizer extra includes
`phonemizers`, the base layer, and a backend with no engine package needs only
that. The Package column names the package that holds the wrapper code. The
last column names each language whose explicit default chain holds the backend.

<!-- backends:start -->
| Backend | Class | Extra | Package | Language default |
|---|---|---|---|---|
| `unicode` | `UnicodeCodepointPhonemizer` | `phonemizers` | scriptconv |  |
| `graphemes` | `GraphemePhonemizer` | `phonemizers` | scriptconv |  |
| `misaki` | `MisakiPhonemizer` | `misaki` | scriptconv-copyleft |  |
| `misaki_en` | `MisakiEnPhonemizer` | `misaki` | scriptconv-copyleft |  |
| `misaki_ja` | `MisakiJaPhonemizer` | `misaki` | scriptconv-copyleft |  |
| `misaki_zh` | `MisakiZhPhonemizer` | `misaki` | scriptconv-copyleft |  |
| `misaki_ko` | `MisakiKoPhonemizer` | `misaki` | scriptconv-copyleft |  |
| `misaki_vi` | `MisakiViPhonemizer` | `misaki` | scriptconv-copyleft |  |
| `espeak` | `EspeakPhonemizer` | `espeak` | scriptconv-copyleft | `gl`, `ru` |
| `gruut` | `GruutPhonemizer` | `gruut` | scriptconv |  |
| `goruut` | `GoruutPhonemizer` | `goruut` | scriptconv |  |
| `epitran` | `EpitranPhonemizer` | `epitran` | scriptconv |  |
| `byt5` | `ByT5Phonemizer` | `byt5` | scriptconv |  |
| `charsiu` | `CharsiuPhonemizer` | `byt5` | scriptconv |  |
| `transphone` | `TransphonePhonemizer` | `transphone` | scriptconv-copyleft |  |
| `phonetisaurus` | `PhonetisaurusPhonemizer` | `phonetisaurus` | scriptconv |  |
| `mwl_phonemizer` | `MirandesePhonemizer` | `o2i` | scriptconv | `mwl` |
| `deepphonemizer` | `DeepPhonemizer` | `en-phonemizers` | scriptconv |  |
| `openphonemizer` | `OpenPhonemizer` | `en-phonemizers` | scriptconv |  |
| `g2pen` | `G2PEnPhonemizer` | `en-phonemizers` | scriptconv |  |
| `dizione` | `DizionePhonemizer` | `en-phonemizers` | scriptconv |  |
| `tugaphone` | `TugaphonePhonemizer` | `pt-phonemizers` | scriptconv | `pt` |
| `g2pfa` | `PersianPhonemizer` | `fa` | scriptconv-copyleft |  |
| `openjtalk` | `OpenJTaklPhonemizer` | `ja-phonemizers` | scriptconv |  |
| `cutlet` | `CutletPhonemizer` | `ja-phonemizers` | scriptconv |  |
| `pykakasi` | `PyKakasiPhonemizer` | `ja-phonemizers` | scriptconv-copyleft |  |
| `cotovia` | `CotoviaPhonemizer` | `gl` | scriptconv-copyleft | `gl` |
| `ahotts` | `AhoTTSPhonemizer` | `eu` | scriptconv-copyleft |  |
| `phonikud` | `PhonikudPhonemizer` | `he` | scriptconv | `he` |
| `mantoq` | `MantoqPhonemizer` | `ar-phonemizers` | scriptconv-nonfree |  |
| `halabi` | `HalabiPhonemizer` | `ar-phonemizers` | scriptconv-nonfree |  |
| `iqra` | `IqraPhonemizer` | `ar-phonemizers` | scriptconv-nonfree |  |
| `viphoneme` | `VIPhonemePhonemizer` | `vi` | scriptconv-nonfree |  |
| `g2pk` | `G2PKPhonemizer` | `ko` | scriptconv-copyleft |  |
| `kog2p` | `KoG2PPhonemizer` | `ko` | scriptconv-copyleft |  |
| `g2pc` | `G2pCPhonemizer` | `zh-phonemizers` | scriptconv |  |
| `g2pm` | `G2pMPhonemizer` | `zh-phonemizers` | scriptconv |  |
| `g2pw` | `G2PWPhonemizer` | `zh-phonemizers` | scriptconv |  |
| `pypinyin` | `PypinyinPhonemizer` | `zh-phonemizers` | scriptconv |  |
| `xpinyin` | `XpinyinPhonemizer` | `zh-phonemizers` | scriptconv |  |
| `jieba` | `JiebaPhonemizer` | `zh-phonemizers` | scriptconv |  |
| `f5tts_char` | `F5TTSCharPhonemizer` | `phonemizers` | scriptconv |  |
| `f5tts_pinyin` | `F5TTSPinyinPhonemizer` | `zh-phonemizers` | scriptconv |  |
| `vosk` | `VoskPhonemizer` | `phonemizers` | scriptconv | `ru` |
| `shami` | `ShamiPhonemizer` | `shami` | scriptconv |  |
| `arbtok` | `ArbtokPhonemizer` | `ar-phonemizers` | scriptconv | `ar` |
| `euskaphone` | `EuskaphonePhonemizer` | `eu` | scriptconv | `eu` |
| `barranquenho` | `BarranquenhoPhonemizer` | `o2i` | scriptconv |  |
| `orthography2ipa` | `Orthography2IPAPhonemizer` | `o2i` | scriptconv | `gl`, `ru` |
| `africa_g2p` | `AfricaG2PPhonemizer` | `africa` | scriptconv-nonfree |  |
| `ghana_g2p` | `GhanaG2PPhonemizer` | `ghana` | scriptconv-nonfree |  |
| `matoub_kab` | `MatoubKabylePhonemizer` | `phonemizers` | scriptconv |  |
<!-- backends:end -->

Two languages list `espeak` and `orthography2ipa` because their chains end
with them. Every other language without an explicit chain resolves to
orthography2ipa when it has a spec for the language, and to espeak otherwise.
`ar` never leaves its chain.

## Model files

ByT5, Charsiu and phonetisaurus never download a model. Each needs a local
path through `model=`, and `get_phonemizer(backend, model=...)` passes that
path to the constructor. Four models download on first use:

| Model | Used by | Cache location |
|---|---|---|
| phonikud ONNX diacritizer | `diacritize(text, "he")` | `scriptconv/phonikud` under `$SCRIPTCONV_CACHE`, else under `$XDG_CACHE_HOME` (default `~/.cache`) |
| Nakdimon diacritizer, pinned to a sha256 | `diacritize(text, "he", diacritizer_model="nakdimon")` | `scriptconv/nakdimon` under the same base directory |
| g2pW polyphone model, pinned to a sha256 | the `g2pw` backend | the Hugging Face cache |
| a DeepPhonemizer checkpoint named in `DeepPhonemizer.MODELS` | the `deepphonemizer` backend | `~/.local/share/deepphonemizer` |

Pass a local path through `diacritizer_model=` or `model=` to skip the
download.

## The phonetisaurus engine and its libraries

The `phonetisaurus` 0.3.0 wheel bundles its executables and most of their
shared objects under `phonetisaurus/lib/<machine>`: `libfst.so.13`,
`libmitlm.so.1`, `libgfortran.so.3` and the OpenFST companions. The binaries
find them only through the `PATH` and `LD_LIBRARY_PATH` that
`phonetisaurus.guess_environment()` builds. `phonetisaurus.predict` and
`phonetisaurus.train` pass that environment to every call. A binary started
with the plain shell environment exits with code 127 from the dynamic loader.

The wrapper only applies a model, and that path needs nothing more. Training
needs one object that the wheel does not bundle:

| Missing object | Needed by | Where it comes from |
|---|---|---|
| `libquadmath.so.0` | `estimate-ngram`, and so `phonetisaurus.train` | the GCC runtime: package `libquadmath0` on Debian and Ubuntu |

`MODEL_SOURCES` on the class names where to get a trained model. To train
one, run `phonetisaurus.train` on a lexicon such as CMUdict.
`tests/test_phonemizers_phonetisaurus_engine.py` runs the real engine when
`SCRIPTCONV_PHONETISAURUS_MODEL` names a trained FST, and skips with the
loader error or the missing model otherwise.

---
[Index](index.md) · [← ovos](ovos.md)
