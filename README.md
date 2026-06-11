# scriptconv

Shared script-conversion core for the TigreGotico voice-AI stack.

Zero runtime dependencies (Python stdlib only).

## Consumers

| Library | What it replaces |
|---------|-----------------|
| **phoonnx** | vendored `thirdparty/arpa2ipa.py`, `bw2ipa.py`, `hangul2ipa.py`, `_MMS_SCRIPTS` in `util.py` |
| **stressonnx** | `Script` enum and `LANG_SCRIPT` / `lang_to_script` in `accentor.py` |
| **orthography2ipa** | optional notation-output layer (does not duplicate `script_distance` typology metrics) |

## Modules

### `scriptconv.scripts`

Writing-system identification and metadata.

- `Script` — frozen dataclass: ISO-15924 code, name, direction, Unicode char ranges.
- `SCRIPT_REGISTRY` — registry of ~30 scripts the org handles.
- `detect_script(text)` — dominant ISO-15924 code by character ranges.
- `char_script(ch)` — script code for a single character.
- `lang_to_script(lang)` — default script for a BCP-47 language tag (~80 languages).
- `normalize_script_tag(label)` — free-form labels to ISO-15924 (`"latin"→"Latn"`,
  `"syllabics"→"Cans"`); ports phoonnx `_MMS_SCRIPTS` and extends it.

### `scriptconv.notation`

Phoneme-notation transcoding (pure data + converters).

- `Notation` enum: `IPA`, `ARPA`, `XSAMPA`, `BUCKWALTER`, `ARABIC`, `LEXIQUE`.
- `arpa_to_ipa` / `ipa_to_arpa` — ARPABET ↔ IPA, stress-digit aware.
  `ipa_to_arpa` flags symbols outside the table with `"?"` (configurable via
  the `unknown` parameter).
  Table derived from [chorusai/arpa2ipa](https://github.com/chorusai/arpa2ipa) (Apache-2.0).
- `xsampa_to_ipa` / `ipa_to_xsampa` — X-SAMPA ↔ IPA, longest-first matching.
- `lexique_to_ipa` / `ipa_to_lexique` — Lexique one-char-per-phoneme ↔ IPA.
  Table: New & Pallier, *Manuel de Lexique 3* v3.11, Tableau 2 (CC BY-SA 4.0).
  Key disambiguation: `N`=ɲ (palatal nasal, e.g. *agneau*),
  `G`=ŋ (velar nasal, English loans, e.g. *camping*),
  `°`=ə (schwa élidable), `3`=ə (schwa non-élidable).
- `buckwalter_to_arabic` / `arabic_to_buckwalter` — Buckwalter ↔ Arabic script.
  Table derived from phoonnx `thirdparty/bw2ipa.py` and standard Buckwalter reference.
- `convert(text, src, dst)` — facade routing through IPA where no direct map exists.

### `scriptconv.translit`

Grapheme-to-IPA transliteration for table-driven scripts.

- `hangul_to_ipa(text)` — Hangul → IPA with full Korean phonological rules
  (palatalization, aspiration, assimilation, tensification, coda neutralization,
  H-deletion, non-coronalization, inter-sonorant voicing, l/ɾ alternation).
  All conversion tables inlined; no external files.
  Derived from [stannam/hangul_to_ipa](https://github.com/stannam/hangul_to_ipa).

## What is intentionally NOT included

- Romanizers (Hepburn, Pinyin, Yale) — notation-specific, belong in consumer libs.
- Arabic diacritization / tashkeel — covered by `arbtok`.
- Typological distance metrics — live in `orthography2ipa.script_distance`; not duplicated here.
- IPA diacritic manipulation (stress insertion/removal) — belongs in `stressonnx`.

## Installation

```bash
pip install scriptconv
```

## Quick start

```python
from scriptconv import (
    detect_script, lang_to_script, normalize_script_tag,
    arpa_to_ipa, ipa_to_arpa,
    xsampa_to_ipa, ipa_to_xsampa,
    lexique_to_ipa, ipa_to_lexique,
    buckwalter_to_arabic, arabic_to_buckwalter,
    hangul_to_ipa,
    convert, Notation,
)

detect_script("안녕하세요")          # "Hang"
lang_to_script("ko")               # "Hang"
normalize_script_tag("syllabics")  # "Cans"

arpa_to_ipa("HH AH0 L OW1")       # "həloʊ"
ipa_to_arpa("həloʊ")              # "AH L OW"

xsampa_to_ipa("S")                 # "ʃ"
ipa_to_xsampa("ʃ")                 # "S"

buckwalter_to_arabic("mrhbA")      # "مرحبا"
arabic_to_buckwalter("مرحبا")     # "mrHbA"

lexique_to_ipa("b§ZuR")           # "bɔ̃ʒuʁ"  (bonjour)
ipa_to_lexique("vɛ̃")              # "v5"  (vin)

hangul_to_ipa("한국어")             # Korean IPA

convert("HH AH0 L OW1", Notation.ARPA, Notation.XSAMPA)
```
