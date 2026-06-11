# scriptconv

**scriptconv** is a zero-dependency Python library for written-script operations:
ISO-15924 script identification and metadata, character-range detection, language-to-script
mapping, lossless phoneme-notation transcoding (IPA ↔ ARPABET ↔ X-SAMPA, IPA ↔ Lexique,
Buckwalter ↔ Arabic script), and orthographic decomposition of Hangul syllable blocks into
jamo letters. Every conversion is a pure data table or arithmetic operation; no linguistic
rules, no external files, no runtime dependencies beyond the Python standard library.

## Scope

scriptconv is exclusively about **written scripts**: identification and metadata,
transliteration between script representations, lossless re-encoding of phoneme symbols
between notation systems, and orthographic decomposition. It never phonemizes — anything
that requires knowing how a language *sounds* (grapheme-to-phoneme rules, allophony,
coarticulation, sandhi) is outside this library's scope.

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
    buckwalter_to_arabic, arabic_to_buckwalter,
    lexique_to_ipa, ipa_to_lexique,
    decompose_hangul,
    convert, Notation,
)

detect_script("안녕하세요")           # "Hang"
lang_to_script("pt-BR")             # "Latn"
normalize_script_tag("syllabics")   # "Cans"

arpa_to_ipa("HH AH0 L OW1")        # "həloʊ"
ipa_to_arpa("həloʊ")               # "HH AX L OW"

xsampa_to_ipa("tS")                 # "tʃ"
ipa_to_xsampa("ɹ")                  # "r\\"

buckwalter_to_arabic("mrHbA")       # "مرحبا"
arabic_to_buckwalter("مرحبا")      # "mrHbA"

lexique_to_ipa("b§ZuR")            # "bɔ̃ʒuʁ"  (bonjour)
ipa_to_lexique("vɛ̃")               # "v5"  (vin)

decompose_hangul("국민")             # "ㄱㅜㄱㅁㅣㄴ"  (orthographic jamo, no assimilation)

convert("NG", Notation.ARPA, Notation.XSAMPA)  # "N"
```

## Modules

| Module | Contents |
|--------|----------|
| `scriptconv.scripts` | `Script` dataclass, `SCRIPT_REGISTRY` (31 scripts), `detect_script`, `char_script`, `lang_to_script`, `normalize_script_tag` |
| `scriptconv.notation` | `Notation` enum, `convert` facade, six pair-wise converters (ARPABET ↔ IPA, X-SAMPA ↔ IPA, Buckwalter ↔ Arabic, Lexique ↔ IPA) |
| `scriptconv.translit` | `decompose_hangul` — Hangul syllable blocks → jamo (orthographic only) |

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

## License and attribution

scriptconv is released under the **Apache-2.0** license.

Derived tables used internally:

| Table | Source | License |
|-------|--------|---------|
| ARPABET ↔ IPA | [chorusai/arpa2ipa](https://github.com/chorusai/arpa2ipa) | Apache-2.0 |
| Buckwalter ↔ Arabic | Tim Buckwalter's transliteration scheme (via pyarabic) | — |
| Lexique phoneme codes | New, B. & Pallier, C. — *Manuel de Lexique 3* v3.11, Tableau 2; [chrplr/openlexicon](https://github.com/chrplr/openlexicon) | CC BY-SA 4.0 |
| Hangul jamo tables | [stannam/hangul_to_ipa](https://github.com/stannam/hangul_to_ipa) | — |
