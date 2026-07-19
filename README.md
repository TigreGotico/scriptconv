# scriptconv

[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Build Tests](https://github.com/TigreGotico/scriptconv/actions/workflows/build-tests.yml/badge.svg?branch=dev)](https://github.com/TigreGotico/scriptconv/actions/workflows/build-tests.yml)
[![PyPI version](https://img.shields.io/pypi/v/scriptconv.svg)](https://pypi.org/project/scriptconv/)

**scriptconv** is a zero-dependency Python library for written-script operations:
ISO-15924 script identification and metadata, character-range detection, language-to-script
mapping, phoneme-notation transcoding (IPA ↔ ARPABET / X-SAMPA / Lexique / Kirshenbaum / Cotovía,
Buckwalter ↔ Arabic script), and orthographic decomposition of Hangul syllable blocks into
jamo letters. Every conversion is a pure data table or arithmetic operation; no linguistic
rules, no external files, no runtime dependencies beyond the Python standard library.

Transcoding is reversible where the target inventory permits — see
[Fidelity guarantees](#fidelity-guarantees) for the exact per-notation guarantees.

## Scope

scriptconv is exclusively about **written scripts**: identification and metadata,
transliteration between script representations, re-encoding of phoneme symbols
between notation systems, and orthographic decomposition. It never phonemizes — anything
that requires knowing how a language *sounds* (grapheme-to-phoneme rules, allophony,
coarticulation, sandhi) is outside this library's scope.

## Installation

```bash
pip install scriptconv
```

### Development

```bash
uv pip install -e '.[test]'
pytest tests/
```

`tests/test_examples.py` runs the scripts under `examples/`, which import the installed
package — install with `-e` first.

## Quick start

```python
from scriptconv import (
    detect_script, char_script, script_distribution, script_runs, base_direction,
    lang_to_script, script_to_langs, normalize_script_tag, SCRIPT_REGISTRY,
    arpa_to_ipa, ipa_to_arpa,
    xsampa_to_ipa, ipa_to_xsampa,
    buckwalter_to_arabic, arabic_to_buckwalter,
    lexique_to_ipa, ipa_to_lexique,
    kirshenbaum_to_ipa, ipa_to_kirshenbaum, cotovia_to_ipa, ipa_to_cotovia, looks_like_ipa,
    decompose_hangul, hira_to_kana, kana_to_hira,
    convert, can_convert, convert_batch, Notation, NOTATION_INFO,
)

detect_script("안녕하세요")           # "Hang"
char_script("ɑ")                    # "Latn" (IPA Extensions)
script_distribution("Hello مرحبا")   # {'Latn': 5, 'Arab': 5}
script_runs("привет hello")          # [('Cyrl', 'привет '), ('Latn', 'hello')]
base_direction("مرحبا بالعالم")      # "rtl"
SCRIPT_REGISTRY["Arab"].script_type  # "abjad"  (typological class)

lang_to_script("pt-BR")             # "Latn"
script_to_langs("Cyrl")             # ['av', 'ba', 'be', 'bg', ...]
normalize_script_tag("syllabics")   # "Cans"
normalize_script_tag("japanese")    # "Hira"

arpa_to_ipa("HH AH0 L OW1")        # "həloʊ"
ipa_to_arpa("həloʊ")               # "HH AX L OW"

xsampa_to_ipa("tS")                 # "tʃ"
ipa_to_xsampa("ɹ")                  # "r\\"

buckwalter_to_arabic("mrHbA")       # "مرحبا"
arabic_to_buckwalter("مرحبا")      # "mrHbA"

lexique_to_ipa("b§ZuR")            # "bɔ̃ʒuʁ"  (bonjour)
ipa_to_lexique("vɛ̃")               # "v5"  (vin)

kirshenbaum_to_ipa("S")             # "ʃ"   (espeak-ng ASCII-IPA)
ipa_to_kirshenbaum("ŋ")             # "N"

cotovia_to_ipa("karro")             # "karo"  (Galician Cotovía TTS notation)
ipa_to_cotovia("ʎ")                 # "L"

looks_like_ipa("pʰɑtʃ")             # True  (heuristic: has IPA-distinctive symbols)
looks_like_ipa("hello")             # False

decompose_hangul("국민")             # "ㄱㅜㄱㅁㅣㄴ"  (orthographic jamo, no assimilation)
hira_to_kana("ひらがな")             # "ヒラガナ"
kana_to_hira("カタカナ")             # "かたかな"

convert("NG", Notation.ARPA, Notation.XSAMPA)  # "N"
convert("HH AH0 L OW1", "arpa", "kirshenbaum") # "h@loU"
can_convert("arpa", "x-sampa")                 # True
can_convert("buckwalter", "ipa")               # False
list(convert_batch(["HH AH0", "AY1"], "arpa", "ipa"))  # ['hə', 'aɪ']

NOTATION_INFO[Notation.ARPA].lossless_from_ipa  # False (restricted inventory)
```

### CLI

```bash
python -m scriptconv convert arpa ipa "HH AH0 L OW1"
python -m scriptconv detect "안녕하세요"
python -m scriptconv distribution "Hello مرحبا"
python -m scriptconv direction "مرحبا بالعالم"
python -m scriptconv decompose "국민"
python -m scriptconv lang ko
```

## Modules

| Module | Contents |
|--------|----------|
| `scriptconv.scripts` | `Script` dataclass (with `script_type`), `SCRIPT_REGISTRY` (34 scripts), `detect_script`, `char_script`, `script_distribution`, `script_runs`, `base_direction`, `lang_to_script`, `script_to_langs`, `normalize_script_tag` |
| `scriptconv.notation` | `Notation` enum, `NotationInfo`/`NOTATION_INFO` fidelity registry, `convert` facade, `can_convert` predicate, `convert_batch` generator, pair-wise converters (ARPABET ↔ IPA, X-SAMPA ↔ IPA, Buckwalter ↔ Arabic, Lexique ↔ IPA, Kirshenbaum ↔ IPA, Cotovía ↔ IPA), `looks_like_ipa` detector |
| `scriptconv.translit` | `decompose_hangul` (Hangul blocks → jamo, compatibility or conjoining), `hira_to_kana`/`kana_to_hira` — all orthographic only |

## Documentation

- [docs/scripts.md](docs/scripts.md) — Script registry, detection, language mapping, label normalisation
- [docs/notation.md](docs/notation.md) — Notation enum, per-pair converter reference, round-trip guarantees
- [docs/translit.md](docs/translit.md) — Hangul decomposition arithmetic and scope boundary

## Examples

Runnable scripts in [examples/](examples/):

| File | Demonstrates |
|------|-------------|
| `01_detect_script.py` | Mixed-script text triage |
| `02_lang_to_script.py` | Language tag → ISO-15924 mapping |
| `03_arpabet_roundtrip.py` | CMUdict-style line → IPA and back |
| `04_xsampa.py` | X-SAMPA ↔ IPA, multi-char longest-first cases |
| `05_buckwalter.py` | Arabic ↔ Buckwalter both directions |
| `06_lexique.py` | French Lexique codes → IPA |
| `07_hangul_decompose.py` | Hangul syllable blocks → jamo letters |
| `08_script_distribution.py` | Character counts per script + base direction |
| `09_script_to_langs.py` | Reverse lookup: script → languages |
| `10_new_labels.py` | New normalize_script_tag labels (japanese, jamo, cjk…) |
| `11_cli.py` | CLI interface: detect, distribution, direction, decompose, lang |
| `12_kirshenbaum.py` | Kirshenbaum (ASCII-IPA) ↔ IPA, and ARPABET → Kirshenbaum routing |
| `13_script_runs.py` | Per-script segmentation of mixed-script text |
| `14_kana_transliteration.py` | Hiragana ↔ Katakana |
| `15_cotovia.py` | Cotovía (Galician TTS notation) ↔ IPA |

## Fidelity guarantees

Transcoding faithfulness depends on the target notation's inventory. IPA is the hub;
notation↔notation goes through IPA. The table below states, for each notation, whether a
round-trip is exact and what happens to a symbol the table does not know.

| Notation | `to_ipa` → `from_ipa` round-trip | `from_ipa` → `to_ipa` round-trip | Unknown-token behaviour |
|----------|----------------------------------|----------------------------------|-------------------------|
| **ARPABET** | Exact for base symbols; **stress digits are dropped** and `AH0`↔`AX` (schwa) is not distinguished | **Lossy** — ARPABET is an English-only inventory, so any IPA symbol outside it becomes the *unknown* placeholder | `arpa_to_ipa`: passed through unchanged. `ipa_to_arpa`: diacritics and suprasegmentals (combining marks, length/stress modifiers) are dropped; other out-of-inventory symbols are replaced with `?` by default (`unknown=` param; `unknown=""` drops) |
| **X-SAMPA** | Exact for all canonical symbols | Exact except aliases (`f\`→ɸ, `&`→æ) normalise to their canonical spelling | Passed through unchanged |
| **Buckwalter ↔ Arabic** | Exact (the `^` shadda alias normalises to canonical `~`; precomposed lam-alef ligatures decompose to two chars, visually identical) | Exact | Passed through unchanged |
| **Lexique ↔ IPA** | Exact except the `°`/`3` schwa pair (both → `ə`; reverse always → `°`) | Exact | Passed through unchanged |
| **Kirshenbaum ↔ IPA** | Exact | **Lossy** — restricted ASCII inventory; IPA outside it passes through | Passed through unchanged |
| **Cotovía ↔ IPA** | Exact except the three `L`/`Z`/`jj` symbols for `ʎ` normalise to `L` | **Lossy** — Galician/Spanish inventory; IPA outside it passes through | Passed through unchanged |

This table is also available programmatically via `NOTATION_INFO`
(`NotationInfo` records with `lossless_to_ipa`, `lossless_from_ipa`,
`token_separated`, and a `reference` citation per notation).

Notes:

- The voiced velar stop is stored as script `ɡ` (U+0261) across all tables; `ipa_to_arpa`
  also accepts ASCII `g` (U+0067) on input.
- Only `ipa_to_arpa` substitutes for unknowns today (because ARPABET is a restricted
  inventory); every other converter passes unknowns through. See
  [docs/notation.md](docs/notation.md) for the per-symbol detail.

## License and attribution

scriptconv is released under the **Apache-2.0** license.

Derived tables used internally:

| Table | Source | License |
|-------|--------|---------|
| ARPABET ↔ IPA | [chorusai/arpa2ipa](https://github.com/chorusai/arpa2ipa) | Apache-2.0 |
| Buckwalter ↔ Arabic | Tim Buckwalter's Arabic transliteration scheme | — (factual 1:1 mapping) |
| Lexique phoneme codes | New, B. & Pallier, C. — *Manuel de Lexique 3* v3.11, Tableau 2; [chrplr/openlexicon](https://github.com/chrplr/openlexicon) | CC BY-SA 4.0 |
| Kirshenbaum ↔ IPA | Kirshenbaum 1993 ASCII-IPA standard (comp.speech), cross-checked against espeak-ng | — (factual symbol mapping) |
| Cotovía ↔ IPA | Universidade de Vigo GTM Cotovía TTS project (`fonemas.cpp`) | — (factual symbol mapping) |
| Hangul jamo tables | [stannam/hangul_to_ipa](https://github.com/stannam/hangul_to_ipa) | — |
