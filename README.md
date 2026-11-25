<div align="center">

# scriptconv

**Every way text is written, and every path between them.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Build Tests](https://github.com/TigreGotico/scriptconv/actions/workflows/build-tests.yml/badge.svg?branch=dev)](https://github.com/TigreGotico/scriptconv/actions/workflows/build-tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/scriptconv.svg)](https://pypi.org/project/scriptconv/)

</div>

<!-- agent-hint
covers: what scriptconv does, the quickstart, the extras and the licences
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
backend, here `pt-phonemizers` for tugaphone. Every call is also a command:

```bash
python -m scriptconv detect "안녕하세요"           # Hang
python -m scriptconv convert arpa ipa "K AE1 T"   # kæt
python -m scriptconv strip tashkeel "مُحَمَّد"       # محمد
python -m scriptconv phonemize pt "Olá mundo"     # ɔˈla ˈmũdu
python -m scriptconv route halabi x-sampa         # the conversion path, hop by hop
```

## Where this fits

Alone: detect, convert and phonemize text with `from scriptconv import convert` and `from scriptconv.phonemizers import phonemize`.
In the stack: the one stop for text conversion. The phoonnx voices take their text path from scriptconv alone, through `TextFrontend`. It calls the stage libraries and phonemizer engines as optional backends.
Through scriptconv: `uv pip install --prerelease=allow "scriptconv[<extra>]"`.

[docs/stack.md](docs/stack.md) shows which library runs each stage,
[docs/backends.md](docs/backends.md) lists every backend with its extra, and
[docs/reference.md](docs/reference.md) gives the signature of each name that a voice imports.

## The mental model

scriptconv is organized around four ideas, layered from identity to sound.

1. **Scripts are identity.** A character belongs to a writing system
   (ISO 15924: `Latn`, `Cyrl`, `Arab`, and so on), detectable from the text
   itself, and identity never changes what the text *means*.

2. **Representations are nodes. Conversions are edges.** IPA, ARPABET,
   hiragana, pinyin, and Cangjie codes are each a node in one conversion
   graph, and asking for `halabi → x-sampa` finds the cheapest path
   (`halabi → ipa → x-sampa`), preferring lossless edges by construction.

3. **Conventions are decorations, not identities.** Arabic vowel marks,
   Hebrew points, Japanese word spacing, and pinyin tone spelling are
   parameters a script's text can carry or omit (`strip`, `restyle`,
   `apply`), never graph nodes.

4. **Fidelity is data.** Whether a conversion round-trips, and what happens
   to a symbol a table does not know, is queryable (`NOTATION_INFO`, the
   `errors=` policy), not folklore buried in docstrings.

The core modules hold no pronunciation rules. Grapheme-to-phoneme inference
needs language knowledge beyond symbol tables, so it lives in the
`phonemizers` subpackage. It joins the graph as one more kind of edge, and
only when the caller asks for it.

## A guided tour

### What script is this? The `scripts` module

```python
from scriptconv import detect_script, script_runs, lang_to_script, base_direction

detect_script("Здравствуйте")        # 'Cyrl'
script_runs("привет hello")          # [('Cyrl', 'привет '), ('Latn', 'hello')]
base_direction("مرحبا hello")        # 'mixed'
lang_to_script("uzb_cyr")            # 'Cyrl'  (ISO 639 codes, BCP-47 tags, _cyr/_lat variants)
```

The returned ISO 15924 tags are **stable API**: downstream code compares
against them directly. `script_runs` follows the UAX #24 model, so combining
marks and neutral characters attach to the run they qualify, and accented
Cyrillic never splits. Details: [docs/scripts.md](docs/scripts.md).

### Same sounds, different symbols: the `notation` module

Nine phoneme notations transcode through an IPA hub: ARPABET, X-SAMPA,
Kirshenbaum, Lexique, Cotovía, RFE, Buckwalter to Arabic, and Halabi (the Nawar Halabi Arabic-Phonetiser notation, popularized by the mantoq package).

```python
from scriptconv import convert, arpa_to_ipa, ipa_to_arpa

convert("HH AH0 L OW1", "arpa", "ipa")        # 'həloʊ'
convert("kˈæt", "ipa", "x-sampa")             # 'k"{t'
arpa_to_ipa("HH AH0 L OW1", stress=True)      # 'həlˈoʊ'
ipa_to_arpa("həlˈoʊ", stress=True)            # 'HH AH0 L OW1'  (exact round-trip)
```

Two contracts make this trustworthy:

- **`errors=`, codecs-style.** Every converter takes
  `errors="pass" | "replace" | "strict" | "ignore"` for symbols outside its
  table. `"strict"` raises `UnknownSymbolError(symbol, position, notation)`.
  Strict drops no mark and accepts spaces, the Unicode White_Space
  characters. The defaults preserve each converter's long-standing behavior.

- **Stress is preserved, not discarded.** With `stress=True`, ARPABET stress
  digits become IPA `ˈ`/`ˌ` placed before the stressed vowel. This is
  reversible by construction, with no syllabification involved. Round-trips
  are exact up to IPA-equivalence. The
  [fidelity table](#fidelity-guarantees) states every residue.

Buckwalter is an independent implementation of the published transliteration
scheme, including alef wasla and the dagger alef (رحمٰن transliterates as
*rHm&#96;n*). The Halabi notation
is the phonetic alphabet of the Halabi Arabic-Phonetiser. Text in it
converts one way to IPA (`halabi_to_ipa("mrHbaa")` → `'mrħbaː'`) and onward
through the graph. Details: [docs/notation.md](docs/notation.md).

### Rewriting the writing: `translit`, `readings`, `cangjie`

Deterministic, table-driven operations on the writing system itself:

```python
from scriptconv import decompose_hangul, hira_to_kana

decompose_hangul("한국")     # 'ㅎㅏㄴㄱㅜㄱ'
hira_to_kana("こんにちは")    # 'コンニチハ'
```

Where a respelling needs a *dictionary*, because the answer is lexical and
not mechanical, it lives behind an extra and raises a clear `ImportError`
when the dictionary is not installed:

```python
from scriptconv import to_hiragana, to_katakana, to_pinyin, to_bopomofo, to_cangjie

to_hiragana("東京タワー")    # 'とうきょうたわー'          pip install scriptconv[ja]
to_katakana("日本語")        # 'ニホンゴ'
to_pinyin("中国人")          # 'zhōng guó rén'           pip install scriptconv[zh]
to_bopomofo("中国")          # 'ㄓㄨㄥ ㄍㄨㄛˊ'
to_cangjie("倉頡")           # 'oiar grmbc'              vendored table, no extra
```

`readings.tokens()` exposes the per-token stream underneath, for consumers
that need word boundaries. The Cangjie table (103,601 glyphs) ships inside
the wheel, so shape-code conversion needs no download and no dependency.
Details: [docs/translit.md](docs/translit.md),
[docs/readings.md](docs/readings.md).

### Marked or unmarked: the `conventions` module

A convention is a decoration a script's orthography can carry or omit. Each
one declares its *styles* and the transitions between them. `strip`/`apply`
are sugar for transitions to and from `"none"`.

```python
from scriptconv import strip, restyle, detect_convention, conventions_for

strip("مُحَمَّد", "tashkeel")                       # 'محمد'
strip("שָׁלוֹם", "niqqud")                          # 'שלום'
strip("わたし は がくせい です", "wakachigaki")      # 'わたしはがくせいです'
restyle("zhōng guó", "pinyin-tone", "number", frm="mark")   # 'zhong1 guo2'
detect_convention("مُحَمَّد", "tashkeel")           # 'marked'
[c.id for c in conventions_for("Arab")]          # ['tashkeel', 'kashida', 'quranic-marks']
```

The registered set covers Arabic `tashkeel`, `kashida`, and `quranic-marks`;
Hebrew `niqqud` and `teamim` (vocalization and cantillation are separate
layers); Japanese `wakachigaki` (spacing is stripped only between Japanese
characters, so "きょうは good day" keeps its space); `pinyin-tone` (mark,
number, or none, deterministic both ways for standard apostrophized
pinyin); and `jamo-form` (compatibility or conjoining repertoires).

Which transitions exist follows one criterion. Stripping and deterministic
re-spelling are always available. Transitions that need a dictionary lookup
(applying wakachigaki means word segmentation) sit behind an extra.

Transitions that need contextual *prediction* (restoring tashkeel) are out
of scope entirely, because that is diacritization, a modelling problem. Their
absence is queryable data rather than a runtime surprise.

The codepoint sets are curated, not naive. Stripping tashkeel **excludes**
U+0653 to U+0655, because in decomposed text those combining marks *are* the
letters آ/أ/إ. A blanket strip would corrupt the consonantal skeleton.
Details: [docs/conventions.md](docs/conventions.md).

### One graph over everything: the `graph` module

Every notation and orthography is a node. Every converter is an edge.
Routing finds the cheapest path and prefers lossless edges, so a lossless
two-hop route beats a lossy shortcut:

```python
from scriptconv import DEFAULT_GRAPH

DEFAULT_GRAPH.convert("こんにちは", "hira", "kana")       # 'コンニチハ'
[f"{e.src}->{e.dst}" for e in DEFAULT_GRAPH.route("arpa", "x-sampa")]
# ['arpa->ipa', 'ipa->x-sampa']
```

Edges are `fn(text, **context)`. Routing context such as `lang=` passes
through opaquely.

Extension is explicit: `graph.extend(register_fn)` returns an extended copy,
and a graph's contents never depend on what happens to be installed.
`DEFAULT_GRAPH` itself contains only orthographic and notation edges.
Details: [docs/graph.md](docs/graph.md).


### From spelling to sound: the `phonemizers` module

The `phonemizers` subpackage wraps grapheme-to-phoneme engines behind one
interface. Some engines ship inside scriptconv: dizione, Leokani G2P, g2pW,
the kolokwa reader, the Vosk Russian rules, the Shami frontend and the Kabyle
Matoub rules. Most others come from the package that an extra installs.
Each language has a default backend, and `override=` picks another one:

```python
from scriptconv.phonemizers import phonemize, Phonemizer

phonemize("kaixo mundua", "eu")                      # 'kai̯ˈʃo munˈdua'   (euskaphone)
phonemize("hello", "en", override=Phonemizer.GRUUT)  # 'hɛlˈoʊ'
```

The default for a language comes from an explicit chain first: Arabic to
arbtok, Basque to euskaphone, Mirandese to its orthography2ipa specs,
Portuguese to tugaphone, Hebrew to phonikud and Liberian English (`lir`) to
kolokwa. Galician goes to Cotovía and
Russian to vosk only when their own notations are requested. Without an
explicit entry, orthography2ipa serves every language it has a spec for, and
espeak is the last resort. Arabic never falls back past arbtok.

Every backend imports lazily. A missing package raises an `ImportError` that
names the extra to install. [docs/backends.md](docs/backends.md) lists every
backend, its class and its extra.

Phonemization joins the graph only on request:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import phonemizers

g = DEFAULT_GRAPH.extend(phonemizers.register)
g.convert("bom dia", "text", "ipa", lang="pt")     # 'ˈbõ ˈdiɐ'
g.can_convert("text", "arpa")                      # True  (chains through IPA)
```

Diacritization restores marks that ordinary spelling leaves out but a
phonemizer needs. `scriptconv.diacritics.diacritize(text, lang)` adds Hebrew
niqqud (phonikud, `he`), Arabic tashkeel (text2tashkeel, `tashkeel`), word
stress for the languages stressonnx covers (`stress`) and European Portuguese
homograph marks (bifonia, `pt`):

```python
from scriptconv.diacritics import diacritize

diacritize("Tenho muita sede hoje.", "pt")   # 'Tenho muita sêde hoje.'
```

A voice reads text through `scriptconv.frontend.TextFrontend`. It splits out
inline `[[phoneme]]` blocks, runs the optional normalisation hook, cuts
sentences, then diacritizes and runs the backend per sentence. A backend that
runs a stage itself is not given that stage twice:

```python
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend

frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.ESPEAK))
frontend.phonemize("Tenho sede [[ˈsedɨ]]. Olá!", Stages(diacritize=True))
# [['t', 'ˌ', 'e', 'ɲ', 'ʊ', ' ', 's', 'ˈ', 'e', 'd', 'ɨ', ' ', 'ˈ', 's', 'e', 'd', 'ɨ'], ['ɔ', 'l', 'ˈ', 'a']]
```

Three rules hold for every backend:

- **scriptconv does not normalise text.** Pass `normalizer=`, a
  `(text, lang) -> str` callable, to run your own normaliser in the pipeline.
  `scriptconv.frontend.spoken_normalizer()` returns `text2spoken.normalize`
  for that hook, behind the `normalize` extra. Without a hook, the text is
  phonemized as written.
- **Some models download on first use, and others never do.** ByT5, Charsiu
  and phonetisaurus need a local `model=` path. These download on first use:
  the phonikud and Nakdimon Hebrew diacritizers, the fp32 text2tashkeel
  weights, the stressonnx models, the g2pW model, the Leokani G2P and
  kolokwa-g2p models, the two data files of the `nemo_ipa` backend and a named
  DeepPhonemizer checkpoint. The `g2pen` backend reads local NLTK data and
  downloads nothing. [docs/backends.md](docs/backends.md#model-files) names
  each cache location.
- **orthography2ipa uses the packaged lexicons.** The `o2i` extra installs
  [o2i-lexicons](https://github.com/TigreGotico/o2i-lexicons), which holds
  the words that the orthography2ipa rules get wrong. Pass
  `packaged_lexicons=False` to `get_phonemizer` to use the rules only.

Details: [docs/phonemizers.md](docs/phonemizers.md),
[docs/frontend.md](docs/frontend.md).

## Fidelity guarantees

Transcoding faithfulness depends on the target notation's inventory. IPA is
the hub, so notation-to-notation conversion goes through IPA. The table
below states, for each notation, whether a round-trip is exact and what
happens to a symbol the table does not know.

Every converter (and `convert()`) accepts a codecs-style `errors=` policy
for symbols outside its table. `"pass"` keeps the symbol (the default
everywhere except `ipa_to_arpa`). `"replace"` substitutes the notation's
placeholder (`?`, the historical `ipa_to_arpa` default, tunable via
`unknown=`). `"ignore"` drops the symbol. `"strict"` raises
`UnknownSymbolError` naming the symbol, its position, and the notation. The
"Unknown-token behaviour" column below describes the per-converter default.

| Notation | `to_ipa` → `from_ipa` round-trip | `from_ipa` → `to_ipa` round-trip | Unknown-token behaviour |
|----------|----------------------------------|----------------------------------|-------------------------|
| **ARPABET** | **Exact with `stress=True`** (digits map to IPA `ˈ`/`ˌ` before the stressed vowel; residues: extended-ARPABET `AX` and `AXR` normalise to CMUdict's `AH0` and `ER0` spellings, stable from the IPA side). Default `stress=False` drops digits, and merges `AH0` with `AX` and `ER0` with `AXR` | **Lossy** (ARPABET is an English-only inventory, so any IPA symbol outside it becomes the *unknown* placeholder) | `arpa_to_ipa`: passed through unchanged. `ipa_to_arpa`: diacritics, suprasegmentals and word gaps are dropped. Other out-of-inventory symbols follow `errors=` (default `"replace"` → `?`) |
| **X-SAMPA** | Exact for every spelling Wells lists; a second spelling (`v\`, `_=`, `_~`) returns as the first (`P`, `=`, `~`) | Exact for every symbol Wells lists, each taken alone, including diacritics and tones | Passed through unchanged |
| **Buckwalter ↔ Arabic** | Exact | Exact. An Arabic presentation form, such as the lam-alef ligature `ﻻ`, returns as the letters it stands for | Follows `errors=` (default: passed through) |
| **Halabi → IPA** | One-directional (gemination and word markers are consumed; there is no IPA to Halabi) | Not applicable | Follows `errors=` (default: passed through) |
| **Lexique ↔ IPA** | Exact except the `°`/`3` schwa pair (both map to `ə`; the reverse always produces `°`) | **Lossy** (French inventory; IPA outside it passes through) | Passed through unchanged |
| **Kirshenbaum ↔ IPA** | **Lossy** (keys such as `F`, `K` and `P`, the digits and punctuation give output that is not IPA) | **Lossy** (restricted ASCII inventory; IPA outside it passes through) | Passed through unchanged |
| **Cotovía ↔ IPA** | Exact except the three `L`/`Z`/`jj` symbols for `ʎ` normalise to `L` | **Lossy** (Galician/Spanish inventory; IPA outside it passes through) | Passed through unchanged |
| **RFE ↔ IPA** | Exact except `ñ`/`n̮` for `ɲ` normalise to `ñ` | **Lossy** (core Spanish/Romance inventory; IPA outside it passes through) | Passed through unchanged |

A test backs every row. `NOTATION_INFO` exposes the same facts to
code, so a program can branch on whether a conversion is safe before making
it. Its flags follow one definition of lossless, which
[docs/notation.md](docs/notation.md#queryable-fidelity-notation_info) states. A
conversion with `stress=True` or another option can be exact where the flag is
`False`, because the flag measures the defaults.


## Extras

The core installs with no dependencies. Each capability is an extra. Some
extras install scriptconv-copyleft or scriptconv-nonfree: see
[Licensing](#licensing). [docs/backends.md](docs/backends.md) names the extra
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

## Related projects

phoonnx builds on scriptconv. scriptconv calls the other libraries below as
optional backends, and they work without scriptconv. pycotovia is the one
exception: its `alphabets` module imports scriptconv to convert its notation.

- [phoonnx](https://github.com/TigreGotico/phoonnx): multilingual ONNX
  text-to-speech. It takes its text path from scriptconv through
  `TextFrontend`.
- [text2spoken](https://github.com/TigreGotico/text2spoken): text
  normalisation, the `normalize` extra.
- [orthography2ipa](https://github.com/TigreGotico/orthography2ipa): a
  data-driven orthography-to-IPA engine, and the usual per-language default.
  Its specs give the Mirandese and Barranquenho backends.
- [arbtok](https://github.com/TigreGotico/arbtok),
  [euskaphone](https://github.com/TigreGotico/euskaphone) and
  [tugaphone](https://github.com/TigreGotico/tugaphone): the dialect-aware
  Arabic, Basque and Portuguese phonemizers.
- [pycotovia](https://github.com/TigreGotico/pycotovia): a pure-Python port
  of the Cotovía Galician TTS engine, whose notation scriptconv transcodes.
- [espyak](https://github.com/TigreGotico/espyak): a pure-Python port of the
  espeak-ng G2P, and the espeak fallback when the binary is absent.

## Documentation and development

[docs/index.md](docs/index.md) lists every page in reading order, and
[docs/stack.md](docs/stack.md) is the place to start. To time a backend, read
[docs/performance.md](docs/performance.md). To write one, read
[docs/extending.md](docs/extending.md).
[AGENTS.md](AGENTS.md) holds the contributor rules.

```bash
uv venv && uv pip install --prerelease=allow -e '.[test]'
pytest tests/
```
