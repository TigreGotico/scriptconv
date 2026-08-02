<div align="center">

# scriptconv

**Every way text is written, and every path between them.**

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Build Tests](https://github.com/TigreGotico/scriptconv/actions/workflows/build-tests.yml/badge.svg?branch=dev)](https://github.com/TigreGotico/scriptconv/actions/workflows/build-tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/scriptconv.svg)](https://pypi.org/project/scriptconv/)

</div>

Text arrives in many representations: scripts (Cyrillic, Hangul, kana),
romanizations (pinyin, Buckwalter), phoneme notations (IPA, ARPABET, X-SAMPA),
input codes (Cangjie), and decorated or undecorated spellings (Arabic with or
without vowel marks, pinyin with tone marks or with digits).

scriptconv identifies which representation a piece of text is in. It
converts between them, and it reports *programmatically* how faithful each
conversion is.

The core is pure Python with zero dependencies. Heavier capabilities, such as
dictionary-backed readings and phonemizer engines, live behind optional
extras and never load unless asked for.

```bash
pip install scriptconv
```

## Five lines to get the idea

```python
from scriptconv import detect_script, convert, strip, restyle, to_pinyin

detect_script("Здравствуйте")                    # 'Cyrl'
convert("HH AH0 L OW1", "arpa", "ipa")           # 'həloʊ'
strip("مُحَمَّد", "tashkeel")                        # 'محمد'
restyle("zhong1 guo2", "pinyin-tone", "mark")    # 'zhōng guó'
to_pinyin("中国人")                               # 'zhōng guó rén'  (zh extra)
```

Everything is also a command:

```bash
python -m scriptconv detect "안녕하세요"           # Hang
python -m scriptconv convert arpa ipa "K AE1 T"   # kæt
python -m scriptconv strip tashkeel "مُحَمَّد"       # محمد
python -m scriptconv route mantoq x-sampa         # the conversion path, hop by hop
```

## The mental model

scriptconv is organized around four ideas, layered from identity to sound.

1. **Scripts are identity.** A character belongs to a writing system
   (ISO 15924: `Latn`, `Cyrl`, `Arab`, and so on), detectable from the text
   itself, and identity never changes what the text *means*.

2. **Representations are nodes. Conversions are edges.** IPA, ARPABET,
   hiragana, pinyin, and Cangjie codes are each a node in one conversion
   graph, and asking for `mantoq → x-sampa` finds the cheapest path
   (`mantoq → ipa → x-sampa`), preferring lossless edges by construction.

3. **Conventions are decorations, not identities.** Arabic vowel marks,
   Hebrew points, Japanese word spacing, and pinyin tone spelling are
   parameters a script's text can carry or omit (`strip`, `restyle`,
   `apply`), never graph nodes.

4. **Fidelity is data.** Whether a conversion round-trips, and what happens
   to a symbol a table does not know, is queryable (`NOTATION_INFO`, the
   `errors=` policy), not folklore buried in docstrings.

The core never invents pronunciation. Grapheme-to-phoneme inference needs
language knowledge beyond symbol tables. When you need it, the
`phonemizers` subpackage wraps real G2P engines behind extras: the same
graph, one more kind of edge, explicitly opted into.

## A guided tour

### What script is this? The `scripts` module

```python
from scriptconv import detect_script, script_runs, lang_to_script, base_direction

detect_script("Здравствуйте")        # 'Cyrl'
script_runs("привет hello")          # [('Cyrl', 'привет '), ('Latn', 'hello')]
base_direction("مرحبا hello")        # 'mixed'
lang_to_script("uzb_cyr")            # 'Cyrl'  (639-1/2/3 codes, BCP-47 tags,
                                     #           informal _cyr/_lat variants
```

The returned ISO 15924 tags are **stable API**: downstream code compares
against them directly. `script_runs` follows the UAX #24 model, so combining
marks and neutral characters attach to the run they qualify, and accented
Cyrillic never splits. Details: [docs/scripts.md](docs/scripts.md).

### Same sounds, different symbols: the `notation` module

Nine phoneme notations transcode through an IPA hub: ARPABET, X-SAMPA,
Kirshenbaum, Lexique, Cotovía, RFE, Buckwalter to Arabic, and mantoq.

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
  The defaults preserve each converter's long-standing behavior.

- **Stress is preserved, not discarded.** With `stress=True`, ARPABET stress
  digits become IPA `ˈ`/`ˌ` placed before the stressed vowel. This is
  reversible by construction, with no syllabification involved. Round-trips
  are exact up to IPA-equivalence. The
  [fidelity table](#fidelity-guarantees) states every residue.

Buckwalter is an independent implementation of the published transliteration
scheme, including alef wasla and the dagger alef (رحمٰن transliterates as
*rHm`n*). Mantoq
is the phonetic alphabet of the Halabi Arabic-Phonetiser. Text in it
converts one way to IPA (`mantoq_to_ipa("mrHbaa")` → `'mrħbaː'`) and onward
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

Wrappers over real G2P engines, such as espeak, gruut, epitran, and ByT5,
and specialized per-language engines, sit behind per-capability extras,
with a default per language and a full override:

```python
from scriptconv.phonemizers import phonemize, Phonemizer

phonemize("kaixo mundua", "eu")        # 'kai̯ʃo mundua'   (euskaphone)
phonemize("hello", "en", override=Phonemizer.GRUUT)
```

Defaults resolve in-house engines first: an explicit per-language chain
(Arabic to arbtok, Basque to euskaphone, Mirandese, Portuguese to
tugaphone, Hebrew to phonikud, Galician to Cotovía, and Russian to vosk for
their own notations), then orthography2ipa wherever it has a language spec,
then espeak as the last resort.

Arabic never falls back past arbtok. A missing engine raises an error
rather than degrading silently. Every backend resolves lazily, and a
missing package raises an `ImportError` naming the extra to install.

Phonemization joins the graph only on request:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import phonemizers

g = DEFAULT_GRAPH.extend(phonemizers.register)
g.convert("bom dia", "text", "ipa", lang="pt")     # 'ˈbõ ˈdʒiɐ'
g.can_convert("text", "arpa")                      # True (chains through IPA)
```

Two design points worth knowing:

- **Normalization is injectable.** TTS stacks expand numbers and dates
  before phonemizing, and that needs language resources scriptconv does
  not ship. Pass `normalizer=` (a `(text, lang) -> str` callable) to run
  yours inside the pipeline. Without it, text is phonemized as-is.

- **Large or licensed model-backed engines never download on their own.**
  ByT5/Charsiu require an explicit local `model=` path, and caching those
  model files is the caller's concern. Small, known-good, unencumbered
  models are the exception: the Hebrew phonikud diacritizer auto-provisions
  its ONNX model to a cache dir on first use (`phonikud_model=` still
  overrides it with a path or callable; the cache location is set via
  `SCRIPTCONV_CACHE` or `XDG_CACHE_HOME`).

**Pre-G2P disambiguation.** `add_diacritics(text, lang, model=None)`
restores information ordinary orthography omits but a G2P needs, before
phonemization. It covers Hebrew niqqud (phonikud), Arabic tashkeel
(text2tashkeel), word stress across 26 stressonnx language tags (East
Slavic; Bulgarian, Macedonian, and Slovene; Latvian; Armenian; Georgian;
and Turkic/Caucasian languages, via `scriptconv[stress]`), and
European-Portuguese heterophonic-homograph sense diacritics (bifonia, via
`scriptconv[pt]`, never applied to `pt-BR`, whose vowel system differs):

```python
from scriptconv.phonemizers import GraphemePhonemizer

p = GraphemePhonemizer()
p.add_diacritics("Tenho muita sede hoje.", "pt")   # 'Tenho muita sêde hoje.' (thirst)
```

Diacritization also joins the graph, like phonemization does, through
`scriptconv.diacritics.register`: a `text -> text-diacritized` edge, opt-in,
with `text -> ipa` routing unchanged:

```python
from scriptconv import diacritics
g = DEFAULT_GRAPH.extend(diacritics.register).extend(phonemizers.register)
g.convert("Tenho muita sede hoje.", "text", "text-diacritized", lang="pt")
# 'Tenho muita sêde hoje.'
```

Stress is unwritten or under-marked in all 26 covered languages. East
Slavic is the clearest case, where unstressed vowels also reduce (for
example, Russian о becomes [ɐ] or [ə]), so a missing mark corrupts more
than prosody there. stressonnx is optional (not yet on PyPI) and emits the
standard combining acute (U+0301) after the stressed vowel.

Details: [docs/phonemizers.md](docs/phonemizers.md).

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
| **ARPABET** | **Lossless with `stress=True`** (digits map to IPA `ˈ`/`ˌ` before the stressed vowel; residues: extended-ARPABET `AX` normalises to CMUdict's `AH0` spelling, and `AH0 R` fuses to the r-colored `AXR0`, stable from the IPA side). Default `stress=False` drops digits and merges `AH0` with `AX` | **Lossy** (ARPABET is an English-only inventory, so any IPA symbol outside it becomes the *unknown* placeholder) | `arpa_to_ipa`: passed through unchanged. `ipa_to_arpa`: diacritics and suprasegmentals are dropped. Other out-of-inventory symbols follow `errors=` (default `"replace"` → `?`) |
| **X-SAMPA** | Exact for all canonical symbols | Exact except aliases (`f\`→ɸ, `&`→æ) normalise to their canonical spelling | Passed through unchanged |
| **Buckwalter ↔ Arabic** | Exact (precomposed lam-alef ligatures decompose to two characters, visually identical) | Exact | Follows `errors=` (default: passed through) |
| **Mantoq → IPA** | One-directional (gemination and word markers are consumed; there is no IPA to Mantoq) | Not applicable | Follows `errors=` (default: passed through) |
| **Lexique ↔ IPA** | Exact except the `°`/`3` schwa pair (both map to `ə`; the reverse always produces `°`) | Exact | Passed through unchanged |
| **Kirshenbaum ↔ IPA** | Exact | **Lossy** (restricted ASCII inventory; IPA outside it passes through) | Passed through unchanged |
| **Cotovía ↔ IPA** | Exact except the three `L`/`Z`/`jj` symbols for `ʎ` normalise to `L` | **Lossy** (Galician/Spanish inventory; IPA outside it passes through) | Passed through unchanged |
| **RFE ↔ IPA** | Exact except `ñ`/`n̮` for `ɲ` normalise to `ñ` | **Lossy** (core Spanish/Romance inventory; IPA outside it passes through) | Passed through unchanged |

Every row is backed by a test. `NOTATION_INFO` exposes the same facts to
code, so a program can branch on whether a conversion is safe before making
it.

## Extras

The core installs with zero dependencies. Capabilities opt in:

| Extra | Enables |
|---|---|
| `ja` / `zh` | Dictionary readings: kanji to kana (pykakasi), hanzi to pinyin/bopomofo (pypinyin) |
| `phonemizers` | The phonemizer base layer (sentence chunking, language matching) |
| `espeak`, `gruut`, `goruut`, `epitran`, `transphone`, `misaki`, `byt5` | Multilingual phonemizer backends |
| `en-phonemizers`, `ja-phonemizers`, `zh-phonemizers`, `ko`, `ar-phonemizers`, `eu`, `pt-phonemizers`, `gl`, `he`, `fa`, `vi`, `mwl`, `shami`, `o2i` | Per-language phonemizer backends |
| `tashkeel` | Arabic diacritization for the phonemizer pipeline (text2tashkeel) |
| `stress` | Word-stress restoration for 26 stressonnx language tags: East Slavic; Bulgarian, Macedonian, and Slovene; Latvian; Armenian; Georgian; and Turkic/Caucasian, for the phonemizer pipeline (stressonnx; not yet on PyPI) |
| `pt` | European-Portuguese heterophonic-homograph sense diacritics for the phonemizer pipeline (bifonia) |

## Licensing

scriptconv is Apache-2.0, with one deliberate, clearly bounded exception:
`scriptconv/phonemizers/_vendored/` quarantines two unpublished third-party
G2P implementations under **their own licenses**: mantoq's phonetisation
core (CC BY-NC 4.0, non-commercial) and KoG2P (GPL-3.0), each with its
LICENSE.md in the directory and in the wheel. Nothing imports them at
package import time. They load only when a caller explicitly requests those
phonemizers, and unencumbered defaults (arbtok for Arabic, g2pk for Korean)
exist for both.

## Related projects

scriptconv sits at the bottom of a family of text and speech libraries that
build on it:

- [phoonnx](https://github.com/TigreGotico/phoonnx): multilingual ONNX
  text-to-speech; consumes scriptconv for scripts, notation, conventions,
  and the whole phonemizer layer.
- [orthography2ipa](https://github.com/TigreGotico/orthography2ipa): a
  data-driven orthography-to-IPA engine, and the usual per-language
  phonemizer default.
- [arbtok](https://github.com/TigreGotico/arbtok): Arabic phonemizer (dialect-aware).
- [euskaphone](https://github.com/TigreGotico/euskaphone): Basque phonemizer (dialect-aware).
- [tugaphone](https://github.com/TigreGotico/tugaphone): Portuguese phonemizer (dialect-aware).
- [mwl_phonemizer](https://github.com/TigreGotico/mwl_phonemizer): Mirandese phonemizer.
- [g2p_barranquenho](https://github.com/TigreGotico/g2p_barranquenho): Barranquenho phonemizer.
- [pycotovia](https://github.com/TigreGotico/pycotovia): a pure-Python
  phonemizer port of the Cotovía Galician TTS engine, whose notation
  scriptconv transcodes.
- [espyak](https://github.com/TigreGotico/espyak): a pure-Python port of
  espeak-ng's G2P, and the espeak fallback when the binary is absent.

## Development

```bash
uv venv && uv pip install -e '.[test]'
pytest tests/
```

The documentation lives in [`docs/`](docs/index.md), one page per module.
</content>
