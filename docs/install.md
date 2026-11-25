# Install, extras and licences

<!-- agent-hint
covers: the extras of scriptconv, the licence of the wheel and of each vendored part, and the sister packages
source: pyproject.toml, scriptconv/phonemizers/registry.py, scripts/check_extra_licences.py, tests/test_wheel_licences.py
generated: no
verify: python scripts/check_doc_page.py docs/install.md
see: index.md, backends.md, phonemizers.md
-->

## Extras

The core installs with no dependencies. Each capability is an extra. Some
extras install scriptconv-copyleft or scriptconv-nonfree: see
[Licensing](#licensing). [backends.md](backends.md) names the extra
of each phonemizer backend.

| Extra | Enables |
|---|---|
| `ja`, `zh` | Dictionary readings: kanji to kana (pykakasi, through scriptconv-copyleft), hanzi to pinyin and bopomofo (pypinyin) |
| `phonemizers` | The phonemizer base layer: sentence chunking (quebra-frases) and language matching (linguatag). Every other phonemizer extra includes it |
| `normalize` | `text2spoken`, the normaliser that `spoken_normalizer()` returns for the `TextFrontend` hook |
| `espeak`, `gruut`, `goruut`, `epitran`, `transphone`, `misaki`, `byt5`, `phonetisaurus` | Multilingual phonemizer backends |
| `en-phonemizers`, `lir`, `ja-phonemizers`, `zh-phonemizers`, `ko`, `ar-phonemizers`, `eu`, `pt-phonemizers`, `gl`, `he`, `fa`, `th`, `vi`, `shami`, `africa`, `ghana` | Per-language phonemizer backends |
| `o2i`, `mwl` | orthography2ipa with o2i-lexicons, and the Mirandese and Barranquenho backends that use its specs. `mwl` installs the same packages as `o2i` |
| `tashkeel` | Arabic diacritization (text2tashkeel) |
| `stress` | Word-stress restoration (stressonnx) for the languages in `scriptconv.diacritics.STRESS_LANGS` |
| `pt` | European Portuguese homograph marks (bifonia) |
| `test` | The test suite and the engines it runs |

## Licensing

The scriptconv wheel is `Apache-2.0 AND MIT AND LicenseRef-CMUdict`. The code
of scriptconv is Apache-2.0. The wheel carries a notice file for each vendored
part in this table:

| Vendored part | Licence | Notice |
|---|---|---|
| Cangjie5 code table | MIT | `scriptconv/data/LICENSE.cangjie5` |
| stannam/hangul_to_ipa converter and tables | MIT | `scriptconv/phonemizers/_thirdparty/LICENSE.hangul_to_ipa` |
| F5-TTS `convert_char_to_pinyin` | MIT | `scriptconv/phonemizers/_thirdparty/LICENSE.f5tts` |
| Nakdimon character tables | MIT | `scriptconv/phonemizers/_thirdparty/nakdimon/LICENSE` |
| g2pW converter and tables | Apache-2.0 | `scriptconv/phonemizers/_thirdparty/g2pw/LICENSE` |
| Matoub-82M Kabyle rules | Apache-2.0 | `scriptconv/phonemizers/_vendored/matoub_kab/LICENSE.md` |
| dizione English phonemizer | Apache-2.0 | `scriptconv/phonemizers/_thirdparty/dizione/LICENSE` |
| dizione dictionary, alignment table and model (CMUdict) | CMUdict | `scriptconv/phonemizers/_thirdparty/dizione/built/LICENSE.cmudict` |
| dizione homograph weights (Wikipedia Homograph Data) | Apache-2.0 | `scriptconv/phonemizers/_thirdparty/dizione/built/LICENSE.homograph-data` |
| Leokani G2P English phonemizer of Milliwatt Labs | MIT | `scriptconv/phonemizers/_thirdparty/leokani/LICENSE` and `NOTICE` |
| NVIDIA NeMo IpaG2p logic, in the `nemo_ipa` backend (no NeMo file) | Apache-2.0 | `scriptconv/phonemizers/_thirdparty/nemo/NOTICE` |

The CMUdict licence is BSD-2-Clause with one added sentence and an
acknowledgement. It has no SPDX identifier, so the wheel names it
`LicenseRef-CMUdict`.

The Vosk Russian rules (`scriptconv/phonemizers/_thirdparty/vosk_g2p.py`, from
alphacep/vosk-tts) and the Shami frontend
(`scriptconv/phonemizers/_thirdparty/shami/`, from hams_tts) are Apache-2.0.
Each names its source and licence in its module docstring, and has no separate
notice file.

The Leokani G2P model files are CC BY 4.0, and the wheel holds the text of
that licence in `scriptconv/phonemizers/_thirdparty/leokani/`. The model of
the `kolokwa` backend is MIT. Neither model is in the wheel: each backend
downloads its model. The `nemo_ipa` backend downloads two NVIDIA files in the
copies of the Magpie TTS checkpoint: a pronunciation dictionary, which is the
CMU Pronouncing Dictionary with IPA pronunciations, and a heteronyms file. Both
are Apache-2.0 in the NeMo tree. Neither file is in the wheel.

The phonemizer wrappers whose code, engine or dependencies are under a
copyleft or a non-commercial licence are in two sister packages:

| Package | Holds | Installed by the extras |
|---|---|---|
| [scriptconv-copyleft](https://github.com/TigreGotico/scriptconv-copyleft) | the espeak, Cotovía, AhoTTS, transphone, misaki, g2pfa, g2pk and KoG2P wrappers, the pykakasi wrapper, the Lithuanian pitch-accent backend `espeak_lt_accent`, the Hebrew `hebrew_ipa`, Japanese `openjtalk_prosody` and Thai `tltk` backends, and the Japanese functions of `readings` | `espeak`, `transphone`, `misaki`, `gl`, `eu`, `fa`, `he`, `ko`, `ja`, `ja-phonemizers`, `th` |
| [scriptconv-nonfree](https://github.com/TigreGotico/scriptconv-nonfree) | the Mantoq, Halabi and Iqra wrappers with the vendored mantoq and iqra_phonetiser, the viphoneme wrapper, and the africa-g2p and ghana-g2p wrappers | `ar-phonemizers`, `vi`, `africa`, `ghana` |

Each sister package states its own licence. scriptconv-nonfree holds code
under CC BY-NC 4.0, which forbids commercial use. The registry imports these
wrappers from the sister package, and without it `get_phonemizer` raises an
`ImportError` that names the extra. The `ar-phonemizers` extra installs
scriptconv-nonfree. To use only arbtok, the Arabic default, install
`scriptconv[phonemizers]` and `arbtok`.

Two dependencies under the LGPL or the GPL stay in the extras of this
package: `distance` and `num2words`. g2p_en declares `distance` and never
imports it. gruut, misaki, openphonemizer and phonikud call num2words for
numbers. `scripts/check_extra_licences.py` resolves every extra and fails on
any other copyleft or non-commercial distribution.
`tests/test_wheel_licences.py` fails when the wheel holds a file under a
licence other than Apache-2.0 or MIT.


---
[Index](index.md) · [← overview](overview.md) · [stack →](stack.md)
