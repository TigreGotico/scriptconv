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
without vowel marks, pinyin with tone marks or with digits). scriptconv
identifies which representation a piece of text is in, converts between them,
and tells you *programmatically* how faithful each conversion is.

The core is **zero-dependency** pure Python. Heavier capabilities —
dictionary-backed readings, phonemizer engines — live behind optional extras
and never load unless asked for.

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

scriptconv is organized around four ideas, layered from identity to sound:

1. **Scripts are identity.** A character belongs to a writing system
   (ISO 15924: `Latn`, `Cyrl`, `Arab`, …). Identity is detectable from the
   text itself and never changes what the text *means*.
2. **Representations are nodes; conversions are edges.** IPA, ARPABET,
   hiragana, pinyin, Cangjie codes — each is a node in one conversion graph.
   Asking for `mantoq → x-sampa` finds the cheapest path
   (`mantoq → ipa → x-sampa`), preferring lossless edges by construction.
3. **Conventions are decorations, not identities.** Arabic vowel marks,
   Hebrew points, Japanese word spacing, pinyin tone spelling — a script's
   text can carry or omit them. They are parameters (`strip`, `restyle`,
   `apply`), never graph nodes.
4. **Fidelity is data.** Whether a conversion round-trips, and what happens
   to a symbol a table doesn't know, is queryable (`NOTATION_INFO`, the
   `errors=` policy) — not folklore buried in docstrings.

The one thing the core never does is *invent pronunciation*:
grapheme-to-phoneme inference needs language knowledge beyond symbol tables.
When you do need it, the `phonemizers` subpackage wraps real G2P engines
behind extras — the same graph, one more kind of edge, explicitly opted into.

## A guided tour

### What script is this? — `scripts`

```python
from scriptconv import detect_script, script_runs, lang_to_script, base_direction

detect_script("Здравствуйте")        # 'Cyrl'
script_runs("привет hello")          # [('Cyrl', 'привет '), ('Latn', 'hello')]
base_direction("مرحبا hello")        # 'mixed'
lang_to_script("uzb_cyr")            # 'Cyrl'  — 639-1/2/3 codes, BCP-47 tags,
                                     #           informal _cyr/_lat variants
```

The returned ISO 15924 tags are **stable API** — downstream code compares
against them directly. `script_runs` follows the UAX #24 model: combining
marks and neutral characters attach to the run they qualify, so accented
Cyrillic never splits. Details: [docs/scripts.md](docs/scripts.md).

### Same sounds, different symbols — `notation`

Nine phoneme notations transcode through an IPA hub: ARPABET, X-SAMPA,
Kirshenbaum, Lexique, Cotovía, RFE, Buckwalter ↔ Arabic, and mantoq.

```python
from scriptconv import convert, arpa_to_ipa, ipa_to_arpa

convert("HH AH0 L OW1", "arpa", "ipa")        # 'həloʊ'
convert("kˈæt", "ipa", "x-sampa")             # 'k"{t'
arpa_to_ipa("HH AH0 L OW1", stress=True)      # 'həlˈoʊ'
ipa_to_arpa("həlˈoʊ", stress=True)            # 'HH AH0 L OW1'  — exact round-trip
```

Two contracts make this trustworthy:

- **`errors=`, codecs-style.** Every converter takes
  `errors="pass" | "replace" | "strict" | "ignore"` for symbols outside its
  table. `"strict"` raises `UnknownSymbolError(symbol, position, notation)`;
  the defaults preserve each converter's long-standing behavior.
- **Stress is preserved, not discarded.** With `stress=True`, ARPABET stress
  digits become IPA `ˈ`/`ˌ` placed before the stressed vowel — reversible by
  construction, no syllabification involved. Round-trips are exact up to
  IPA-equivalence; the [fidelity table](#fidelity-guarantees) states every
  residue.

Buckwalter is an independent implementation of the published transliteration
scheme, including alef wasla and the dagger alef (رحمٰن ↔ ``rHm`n``). Mantoq
is the phonetic alphabet of the Halabi Arabic-Phonetiser — text in it
converts one-way to IPA (`mantoq_to_ipa("mrHbaa")` → `'mrħbaː'`) and onward
through the graph. Details: [docs/notation.md](docs/notation.md).

### Rewriting the writing — `translit`, `readings`, `cangjie`

Deterministic, table-driven operations on the writing system itself:

```python
from scriptconv import decompose_hangul, hira_to_kana

decompose_hangul("한국")     # 'ㅎㅏㄴㄱㅜㄱ'
hira_to_kana("こんにちは")    # 'コンニチハ'
```

Where a respelling needs a *dictionary* — because the answer is lexical, not
mechanical — it lives behind an extra and raises a clear `ImportError` when
the dictionary isn't installed:

```python
from scriptconv import to_hiragana, to_katakana, to_pinyin, to_bopomofo, to_cangjie

to_hiragana("東京タワー")    # 'とうきょうたわー'          pip install scriptconv[ja]
to_katakana("日本語")        # 'ニホンゴ'
to_pinyin("中国人")          # 'zhōng guó rén'           pip install scriptconv[zh]
to_bopomofo("中国")          # 'ㄓㄨㄥ ㄍㄨㄛˊ'
to_cangjie("倉頡")           # 'oiar grmbc'              vendored table, no extra
```

`readings.tokens()` exposes the per-token stream underneath for consumers
that need word boundaries; the Cangjie table (103,601 glyphs) ships inside
the wheel, so shape-code conversion needs no download and no dependency.
Details: [docs/translit.md](docs/translit.md),
[docs/readings.md](docs/readings.md).

### Marked or unmarked — `conventions`

A convention is a decoration a script's orthography can carry or omit. Each
one declares its *styles* and the transitions between them; `strip`/`apply`
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

The registered set: Arabic `tashkeel`, `kashida`, `quranic-marks`; Hebrew
`niqqud` and `teamim` (vocalization and cantillation are separate layers);
Japanese `wakachigaki` (spacing is stripped only between Japanese characters —
"きょうは good day" keeps its space); `pinyin-tone` (mark ↔ number ↔ none,
deterministic both ways for standard apostrophized pinyin); and `jamo-form`
(compatibility ↔ conjoining repertoires).

Which transitions exist follows one criterion: stripping and deterministic
re-spelling are always available; transitions needing a dictionary lookup
(applying wakachigaki = word segmentation) sit behind an extra; transitions
needing contextual *prediction* (restoring tashkeel) are out of scope
entirely — that is diacritization, a modelling problem — and their absence is
queryable data rather than a runtime surprise.

The codepoint sets are curated, not naive: stripping tashkeel **excludes**
U+0653–0655 because in decomposed text those combining marks *are* the
letters آ/أ/إ — a blanket strip corrupts the consonantal skeleton.
Details: [docs/conventions.md](docs/conventions.md).

### One graph over everything — `graph`

Every notation and orthography is a node; every converter an edge; routing
finds the cheapest path and prefers lossless edges, so a lossless two-hop
beats a lossy shortcut:

```python
from scriptconv import DEFAULT_GRAPH

DEFAULT_GRAPH.convert("こんにちは", "hira", "kana")       # 'コンニチハ'
[f"{e.src}->{e.dst}" for e in DEFAULT_GRAPH.route("arpa", "x-sampa")]
# ['arpa->ipa', 'ipa->x-sampa']
```

Edges are `fn(text, **context)` — routing context like `lang=` passes through
opaquely. Extension is explicit: `graph.extend(register_fn)` returns an
extended copy, and a graph's contents never depend on what happens to be
installed. `DEFAULT_GRAPH` itself contains orthographic and notation edges
only. Details: [docs/graph.md](docs/graph.md).

### From spelling to sound — `phonemizers`

Wrappers over real G2P engines — espeak, gruut, epitran, ByT5, and
specialized per-language engines — behind per-capability extras, with a
default per language and full override:

```python
from scriptconv.phonemizers import phonemize, Phonemizer

phonemize("kaixo mundua", "eu")        # 'kai̯ʃo mundua'   (euskaphone)
phonemize("hello", "en", override=Phonemizer.GRUUT)
```

Defaults resolve in-house engines first: an explicit per-language chain
(Arabic → arbtok, Basque → euskaphone, Mirandese, Portuguese → tugaphone,
Hebrew → phonikud, Galician → Cotovía for its own notation), then
orthography2ipa wherever it has a language spec, then espeak as the last
resort. Arabic never falls back past arbtok — a missing engine raises rather
than silently degrading. Every backend resolves lazily; a missing package
raises an `ImportError` naming the extra to install.

Phonemization joins the graph only on request:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import phonemizers

g = DEFAULT_GRAPH.extend(phonemizers.register)
g.convert("bom dia", "text", "ipa", lang="pt")     # 'ˈbõ ˈdʒiɐ'
g.can_convert("text", "arpa")                      # True — chains through IPA
```

Two design points worth knowing:

- **Normalization is injectable.** TTS stacks expand numbers and dates before
  phonemizing; that needs language resources scriptconv doesn't ship. Pass
  `normalizer=` (a `(text, lang) -> str` callable) to run yours inside the
  pipeline; without it, text is phonemized as-is.
- **Model-backed engines never download.** ByT5/Charsiu require an explicit
  local `model=` path; resolving and caching model files is the caller's
  concern.

Details: [docs/phonemizers.md](docs/phonemizers.md).

## Fidelity guarantees

Transcoding faithfulness depends on the target notation's inventory. IPA is
the hub; notation↔notation goes through IPA. The table below states, for each
notation, whether a round-trip is exact and what happens to a symbol the
table does not know.

Every converter (and `convert()`) accepts a codecs-style `errors=` policy for
symbols outside its table: `"pass"` keeps the symbol (the default everywhere
except `ipa_to_arpa`), `"replace"` substitutes the notation's placeholder
(`?`; the historical `ipa_to_arpa` default, tunable via `unknown=`),
`"ignore"` drops it, and `"strict"` raises `UnknownSymbolError` naming the
symbol, its position, and the notation. The "Unknown-token behaviour" column
below describes the per-converter default.

| Notation | `to_ipa` → `from_ipa` round-trip | `from_ipa` → `to_ipa` round-trip | Unknown-token behaviour |
|----------|----------------------------------|----------------------------------|-------------------------|
| **ARPABET** | **Lossless with `stress=True`** (digits ↔ IPA `ˈ`/`ˌ` before the stressed vowel; residues: extended-ARPABET `AX` normalises to CMUdict's `AH0` spelling, and `AH0 R` fuses to the r-colored `AXR0` — stable from the IPA side). Default `stress=False` drops digits and merges `AH0`↔`AX` | **Lossy** — ARPABET is an English-only inventory, so any IPA symbol outside it becomes the *unknown* placeholder | `arpa_to_ipa`: passed through unchanged. `ipa_to_arpa`: diacritics and suprasegmentals are dropped; other out-of-inventory symbols follow `errors=` (default `"replace"` → `?`) |
| **X-SAMPA** | Exact for all canonical symbols | Exact except aliases (`f\`→ɸ, `&`→æ) normalise to their canonical spelling | Passed through unchanged |
| **Buckwalter ↔ Arabic** | Exact (precomposed lam-alef ligatures decompose to two chars, visually identical) | Exact | Follows `errors=` (default: passed through) |
| **Mantoq → IPA** | One-directional (gemination/word markers consumed; no IPA→Mantoq) | — | Follows `errors=` (default: passed through) |
| **Lexique ↔ IPA** | Exact except the `°`/`3` schwa pair (both → `ə`; reverse always → `°`) | Exact | Passed through unchanged |
| **Kirshenbaum ↔ IPA** | Exact | **Lossy** — restricted ASCII inventory; IPA outside it passes through | Passed through unchanged |
| **Cotovía ↔ IPA** | Exact except the three `L`/`Z`/`jj` symbols for `ʎ` normalise to `L` | **Lossy** — Galician/Spanish inventory; IPA outside it passes through | Passed through unchanged |
| **RFE ↔ IPA** | Exact except `ñ`/`n̮` for `ɲ` normalise to `ñ` | **Lossy** — core Spanish/Romance inventory; IPA outside it passes through | Passed through unchanged |

Every row is backed by a test; `NOTATION_INFO` exposes the same facts to
code, so a program can branch on whether a conversion is safe before making
it.

## Extras

The core installs with zero dependencies. Capabilities opt in:

| Extra | Enables |
|---|---|
| `ja` / `zh` | Dictionary readings: kanji→kana (pykakasi), hanzi→pinyin/bopomofo (pypinyin) |
| `phonemizers` | The phonemizer base layer (sentence chunking, language matching) |
| `espeak`, `gruut`, `goruut`, `epitran`, `transphone`, `misaki`, `byt5` | Multilingual phonemizer backends |
| `en-phonemizers`, `ja-phonemizers`, `zh-phonemizers`, `ko`, `ar-phonemizers`, `eu`, `pt-phonemizers`, `gl`, `he`, `fa`, `vi`, `mwl`, `shami`, `o2i` | Per-language phonemizer backends |
| `tashkeel` | Arabic diacritization for the phonemizer pipeline (text2tashkeel) |

## Licensing

scriptconv is Apache-2.0, with one deliberate, clearly-bounded exception:
`scriptconv/phonemizers/_vendored/` quarantines two unpublished third-party
G2P implementations under **their own licenses** — mantoq's phonetisation
core (CC BY-NC 4.0, non-commercial) and KoG2P (GPL-3.0) — each with its
LICENSE.md in the directory and in the wheel. Nothing imports them at package
import time; they load only when a caller explicitly requests those
phonemizers, and unencumbered defaults (arbtok for Arabic, g2pk for Korean)
exist for both.

## Development

```bash
uv venv && uv pip install -e '.[test]'
pytest tests/
```

The documentation lives in [`docs/`](docs/index.md), one page per module.
