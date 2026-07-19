# scriptconv.notation

Phoneme-notation transcoding. All tables are pure Python data; zero runtime dependencies.

```python
from scriptconv.notation import (
    Notation, convert, can_convert, convert_batch,
    arpa_to_ipa, ipa_to_arpa,
    xsampa_to_ipa, ipa_to_xsampa,
    buckwalter_to_arabic, arabic_to_buckwalter,
    lexique_to_ipa, ipa_to_lexique,
)
```

---

## Notation enum

```python
class Notation(str, Enum):
    IPA        = "ipa"
    ARPA       = "arpa"
    XSAMPA     = "x-sampa"
    BUCKWALTER = "buckwalter"
    ARABIC     = "arabic"
    LEXIQUE    = "lexique"
```

`Notation` is a `str` subclass. Its string values (`"ipa"`, `"arpa"`, etc.) are accepted
anywhere a `Notation` is expected:

```python
convert("S", "x-sampa", "ipa")            # string values
convert("S", Notation.XSAMPA, Notation.IPA)  # enum members — equivalent
```

---

## convert — facade

```python
def convert(text: str, src: str | Notation, dst: str | Notation) -> str
```

Routes a conversion through the appropriate pair function, or chains through IPA when
no direct map exists.

**Direct paths**:

| src | dst | Function called |
|-----|-----|----------------|
| `arpa` | `ipa` | `arpa_to_ipa` |
| `ipa` | `arpa` | `ipa_to_arpa` |
| `x-sampa` | `ipa` | `xsampa_to_ipa` |
| `ipa` | `x-sampa` | `ipa_to_xsampa` |
| `lexique` | `ipa` | `lexique_to_ipa` |
| `ipa` | `lexique` | `ipa_to_lexique` |
| `buckwalter` | `arabic` | `buckwalter_to_arabic` |
| `arabic` | `buckwalter` | `arabic_to_buckwalter` |

**Indirect paths** (routed through IPA):

| src | dst | Route |
|-----|-----|-------|
| `arpa` | `x-sampa` | arpa → IPA → x-sampa |
| `arpa` | `lexique` | arpa → IPA → lexique |
| `x-sampa` | `arpa` | x-sampa → IPA → arpa |
| `x-sampa` | `lexique` | x-sampa → IPA → lexique |
| `lexique` | `arpa` | lexique → IPA → arpa |
| `lexique` | `x-sampa` | lexique → IPA → x-sampa |

**Unsupported paths** raise `ValueError`. For example, `arabic → ipa` is not supported
because the Buckwalter table maps to script characters, not to IPA phonemes; IPA for
Arabic requires a phonemizer.

```python
convert("NG", "arpa", "x-sampa")   # "N"
convert("Sa", "lexique", "x-sampa")  # "Sa"  (ʃ→S, a→a)
```

**Identity**: `convert(text, x, x)` always returns `text` unchanged.

---

## ARPABET ↔ IPA

Table derived from [chorusai/arpa2ipa](https://github.com/chorusai/arpa2ipa) (Apache-2.0).

### arpa_to_ipa

```python
def arpa_to_ipa(arpa_sequence: str) -> str
```

Converts a space-separated ARPABET token sequence to an IPA string. Stress digits
(`0`, `1`, `2`) are stripped before lookup. Unknown tokens are passed through unchanged.

**Stress digit handling**:
- `AH0` is special-cased: maps to `ə` (schwa), not `ʌ`.
- `AH1`, `AH2` → `ʌ` (stressed vowel).
- All other `TOKEN0`/`TOKEN1`/`TOKEN2` → same IPA as `TOKEN` (stress is lost in IPA output).

```python
arpa_to_ipa("HH AH0 L OW1")   # "həloʊ"
arpa_to_ipa("JH AH1 S T")     # "dʒʌst"
arpa_to_ipa("TH AE1 NG K S")  # "θæŋks"
arpa_to_ipa("AH0")            # "ə"
arpa_to_ipa("AH1")            # "ʌ"
arpa_to_ipa("UNKNOWN")        # "UNKNOWN"  (passed through)
```

### ipa_to_arpa

```python
def ipa_to_arpa(ipa_string: str, unknown: str = "?") -> str
```

Converts an IPA string to a space-separated ARPABET sequence. Matches the longest IPA
symbol at each position. Characters not in the ARPABET table are replaced by `unknown`
(default `"?"`); pass `unknown=""` to drop them silently.

```python
ipa_to_arpa("həloʊ")   # "HH AX L OW"
ipa_to_arpa("ŋ")       # "NG"
ipa_to_arpa("ɸ")       # "?"
ipa_to_arpa("ɸ", unknown="")  # ""
```

**Stress loss**: IPA → ARPABET is lossy for stress. The base ARPABET form (no digit) is
always returned; stress digits cannot be recovered from plain IPA.

**AH0/AX asymmetry**: `AH0` (unstressed `AH`) maps to `ə` in the forward direction;
the reverse maps `ə` to `AX` (the CMU `AX` token, which also denotes schwa). This is a
known asymmetry: `arpa_to_ipa("AH0") == "ə"` but `ipa_to_arpa("ə") == "AX"`.

### Round-trip guarantees

ARPA → IPA → ARPA is lossless for consonants and for vowels that have a unique IPA
symbol:

```
P → p → P    B → b → B    TH → θ → TH    NG → ŋ → NG   ✓
```

It is **lossy** for:
- Stress digits: `AH1` → `ʌ` → `AH` (digit lost).
- `AH0` → `ə` → `AX` (token changes).

IPA → ARPA → IPA is also lossy because the reverse table uses base ARPABET forms.

---

## X-SAMPA ↔ IPA

Standard X-SAMPA mapping. Reference: [X-SAMPA on Wikipedia](https://en.wikipedia.org/wiki/X-SAMPA).

### xsampa_to_ipa

```python
def xsampa_to_ipa(xsampa: str) -> str
```

Converts an X-SAMPA string to IPA. Multi-character symbols are matched **longest-first**
at each position. Unknown characters are passed through unchanged.

**Key multi-character cases** (longest-first matching is required):

| X-SAMPA | IPA | Note |
|---------|-----|------|
| `tS` | `tʃ` | palato-alveolar affricate; must not split as `t` + `S`=`ʃ` |
| `dZ` | `dʒ` | voiced affricate |
| `r\` | `ɹ` | approximant r; must match before plain `r` |
| `ts\`` | `ʈ͡ʂ` | retroflex affricate; longest match |
| `@\` | `ɘ` | close-mid central unrounded; before `@`=`ə` |
| `@\`` | `ɚ` | r-coloured schwa; before `@` |
| `N\` | `ɴ` | uvular nasal; before `N`=`ŋ` |
| `G\` | `ɢ` | voiced uvular stop; before `G`=`ɣ` |

```python
xsampa_to_ipa("S")      # "ʃ"
xsampa_to_ipa("Z")      # "ʒ"
xsampa_to_ipa("@")      # "ə"
xsampa_to_ipa("tS")     # "tʃ"  (not "tʃ" split)
xsampa_to_ipa("r\\")    # "ɹ"
xsampa_to_ipa('"tS@n')  # "ˈtʃən"
```

### ipa_to_xsampa

```python
def ipa_to_xsampa(ipa: str) -> str
```

Converts an IPA string to X-SAMPA. Longest-first matching on IPA keys. Unknown IPA
characters are passed through.

```python
ipa_to_xsampa("ʃ")   # "S"
ipa_to_xsampa("ə")   # "@"
ipa_to_xsampa("tʃ")  # "tS"
ipa_to_xsampa("ɹ")   # "r\\"
ipa_to_xsampa("æ")   # "{"
ipa_to_xsampa("ʉ")   # "}"
```

### Round-trip guarantees

IPA → X-SAMPA → IPA is lossless for all symbols in the table. X-SAMPA → IPA → X-SAMPA
is lossless for symbols with a unique IPA counterpart; aliases (`&` = `{` = `æ`) map
to the canonical X-SAMPA form on the way back.

**Alias collisions** — several X-SAMPA symbols map to the same IPA value. The reverse
table uses the canonical form (first defined), so round-tripping non-canonical aliases
produces the canonical form:

| X-SAMPA aliases | IPA | Canonical X-SAMPA |
|-----------------|-----|--------------------|
| `{` or `&` | æ | `{` |
| `f\` or `p\` | ɸ | `p\` |
| `r\` or `4` | ɹ | `r\` |

```python
ipa_to_xsampa("æ")   # "{"  (canonical, not "&")
ipa_to_xsampa("ɸ")   # "p\\"  (not "f\\")
```

---

## Buckwalter ↔ Arabic script

Table follows Tim Buckwalter's published Arabic transliteration scheme — a
1:1 factual mapping between Arabic letters and ASCII characters.

### buckwalter_to_arabic

```python
def buckwalter_to_arabic(bw: str) -> str
```

Converts a Buckwalter-encoded string to Arabic Unicode. Unknown characters are passed
through unchanged. The mapping is character-by-character (no context rules).

```python
buckwalter_to_arabic("mrHbA")   # "مرحبا"
buckwalter_to_arabic("A")       # "ا"   (alef)
buckwalter_to_arabic("p")       # "ة"   (ta marbuta)
```

### arabic_to_buckwalter

```python
def arabic_to_buckwalter(arabic: str) -> str
```

Converts Arabic Unicode to Buckwalter transliteration. Unknown characters are passed
through unchanged.

```python
arabic_to_buckwalter("مرحبا")   # "mrHbA"
arabic_to_buckwalter("ا")       # "A"
```

### Buckwalter symbol table

| BW | Arabic | Name |
|----|--------|------|
| `'` | ء | hamza |
| `\|` | آ | alef madda |
| `>` | أ | alef + hamza above |
| `&` | ؤ | waw + hamza |
| `<` | إ | alef + hamza below |
| `}` | ئ | ya + hamza |
| `A` | ا | alef |
| `b` | ب | ba |
| `p` | ة | ta marbuta |
| `t` | ت | ta |
| `v` | ث | tha |
| `j` | ج | jim |
| `H` | ح | ha (pharyngeal) |
| `x` | خ | kha |
| `d` | د | dal |
| `*` | ذ | dhal |
| `r` | ر | ra |
| `z` | ز | zayn |
| `s` | س | sin |
| `$` | ش | shin |
| `S` | ص | sad |
| `D` | ض | dad |
| `T` | ط | ta (emphatic) |
| `Z` | ظ | dha (emphatic) |
| `E` | ع | ain |
| `g` | غ | ghayn |
| `f` | ف | fa |
| `q` | ق | qaf |
| `k` | ك | kaf |
| `l` | ل | lam |
| `m` | م | mim |
| `n` | ن | nun |
| `h` | ه | ha |
| `w` | و | waw |
| `Y` | ى | alef maqsura |
| `y` | ي | ya |
| `a` | َ | fatha (short vowel) |
| `u` | ُ | damma (short vowel) |
| `i` | ِ | kasra (short vowel) |
| `~` | ّ | shadda (gemination) |
| `o` | ْ | sukun |
| `F` | ً | tanwin fath |
| `N` | ٌ | tanwin damm |
| `K` | ٍ | tanwin kasr |
| `_` | ـ | tatweel |
| `^` | ّ | shadda (alias for `~`) |

**Shadda alias note**: both `~` and `^` map to the shadda character (U+0651) in the
forward direction. In the reverse direction, shadda maps to the canonical `~`, so
standard Buckwalter round-trips (`~` → ّ → `~`) are exact; the `^` alias is accepted on
input but not emitted.

---

## Lexique ↔ IPA

Source: New, B. & Pallier, C. — *Manuel de Lexique 3* v3.11, Tableau 2 (p. 12).
[chrplr/openlexicon](https://github.com/chrplr/openlexicon), CC BY-SA 4.0.

Lexique uses a **one-character-per-phoneme** notation for French. Each character in the
Lexique phoneme string represents exactly one phoneme.

### lexique_to_ipa

```python
def lexique_to_ipa(lexique: str) -> str
```

Converts a Lexique phoneme-code string to IPA. Each character is looked up
independently (no multi-character symbols). Unknown characters are passed through.

```python
lexique_to_ipa("b§ZuR")   # "bɔ̃ʒuʁ"  (bonjour)
lexique_to_ipa("v5")      # "vɛ̃"     (vin)
lexique_to_ipa("aNo")     # "aɲo"    (agneau — N=ɲ palatal nasal)
lexique_to_ipa("kaGiG")   # "kaŋiŋ"  (camping — G=ŋ velar nasal)
lexique_to_ipa("d@s")     # "dɑ̃s"   (dans)
lexique_to_ipa("abd°Ra")  # "abdəʁa" (° = schwa élidable)
```

### ipa_to_lexique

```python
def ipa_to_lexique(ipa: str) -> str
```

Converts an IPA string to Lexique codes. Longest-first matching on IPA keys. Symbols
outside the French Lexique inventory are passed through.

```python
ipa_to_lexique("bɔ̃ʒuʁ")  # "b§ZuR"
ipa_to_lexique("vɛ̃")     # "v5"
ipa_to_lexique("dø")      # "d2"
ipa_to_lexique("pœʁ")     # "p9R"
```

### Full Lexique code table

Verified against *Manuel de Lexique 3* v3.11, Tableau 2.

| Code | IPA | Example |
|------|-----|---------|
| `a` | a | *bat*, *plat* |
| `i` | i | *lit*, *émis* |
| `y` | y | *lu* |
| `u` | u | *roue* |
| `o` | o | *peau*, *mot* (o fermé) |
| `O` | ɔ | *éloge*, *fort* (o ouvert) |
| `e` | e | *été* (e fermé) |
| `E` | ɛ | *paire*, *treize* (e ouvert) |
| `°` | ə | schwa élidable (*abordera*) |
| `3` | ə | schwa non-élidable (*parvenu*) |
| `2` | ø | *deux* (eu fermé) |
| `9` | œ | *œuf*, *peur* (eu ouvert) |
| `5` | ɛ̃ | *cinq*, *linge* (nasale in) |
| `1` | œ̃ | *un*, *parfum* (nasale un) |
| `@` | ɑ̃ | *ange* (nasale an) |
| `§` | ɔ̃ | *on*, *savon* (nasale on) |
| `j` | j | *yeux*, *paille* |
| `8` | ɥ | *huit*, *lui* |
| `w` | w | *oui*, *nouer* |
| `p` | p | *père*, *soupe* |
| `b` | b | *bon*, *robe* |
| `t` | t | *terre*, *vite* |
| `d` | d | *dans*, *aide* |
| `k` | k | *carré*, *laque* |
| `g` | ɡ | *gare*, *bague* |
| `f` | f | *feu*, *neuf* |
| `v` | v | *vous*, *rêve* |
| `s` | s | *sale*, *dessous* |
| `z` | z | *zéro*, *maison* |
| `S` | ʃ | *chat*, *tâche* |
| `Z` | ʒ | *gilet*, *mijoter* |
| `m` | m | *main*, *femme* |
| `n` | n | *nous*, *tonne* |
| `N` | ɲ | *agneau*, *vigne* (nasale palatale) |
| `l` | l | *lent*, *sol* |
| `R` | ʁ | *rue*, *venir* |
| `x` | x | *jota* (emprunt espagnol) |
| `G` | ŋ | *camping* (ng, emprunt anglais) |

**Critical disambiguation**:
- `N` = **ɲ** (palatal nasal), not ŋ. Example: *agneau* → `aNo`.
- `G` = **ŋ** (velar nasal, English loanwords). Example: *camping* → `kaGiG`.
- `°` and `3` both map to **ə** in the IPA output. In the reverse direction, ə maps
  to `°` (first occurrence wins). Round-trips of strings containing `3` will produce
  `°`.

### Round-trip guarantees

Lexique → IPA → Lexique is lossless except for the `°`/`3` schwa pair (both map to `ə`
in IPA; reverse always produces `°`). All other phonemes round-trip exactly.

---

## can_convert — predicate

```python
def can_convert(src: str | Notation, dst: str | Notation) -> bool
```

Returns `True` if a conversion from *src* to *dst* is supported (direct or indirect
through IPA). Does not perform any conversion.

```python
can_convert("arpa", "ipa")         # True  (direct)
can_convert("arpa", "x-sampa")     # True  (indirect: arpa→ipa→x-sampa)
can_convert("buckwalter", "ipa")   # False (not supported)
can_convert("ipa", "ipa")          # False (identity — use convert() instead)
```

---

## convert_batch — line-by-line generator

```python
def convert_batch(
    lines: Iterable[str],
    src: str | Notation,
    dst: str | Notation,
) -> Generator[str, None, None]
```

Converts each line from *src* to *dst* notation, yielding results. Blank lines are
yielded unchanged. Useful for processing files or piped input.

```python
lines = ["HH AH0 L OW1", "", "AY1"]
list(convert_batch(lines, "arpa", "ipa"))
# ['həloʊ', '', 'aɪ']
```

## Kirshenbaum (ASCII-IPA) ↔ IPA

Kirshenbaum is the ASCII phonetic alphabet defined by Kirshenbaum 1993
(comp.speech), also used natively by espeak-ng. The single-character mapping is
the factual ASCII → IPA codepoint correspondence of that standard (index *i* →
the IPA codepoint for ASCII `0x20+i`), cross-checked against espeak-ng.

```python
kirshenbaum_to_ipa("S")   # "ʃ"
ipa_to_kirshenbaum("ŋ")   # "N"
```

Each character maps independently; characters outside the table pass through.
`<notation> → IPA → <notation>` round-trips are exact from the Kirshenbaum side;
`IPA → Kirshenbaum → IPA` is lossy for IPA outside the ASCII inventory.

## Queryable fidelity — `NOTATION_INFO`

The fidelity guarantees are exposed as data so callers can branch on them
instead of reading prose:

```python
from scriptconv import NOTATION_INFO, Notation
info = NOTATION_INFO[Notation.ARPA]
info.lossless_from_ipa   # False — restricted English inventory
info.token_separated     # True  — space-separated ARPABET tokens
info.reference           # citation URL/string
```

Each `NotationInfo` carries `lossless_to_ipa`, `lossless_from_ipa`,
`token_separated`, and `reference`.

## Notation detection — `looks_like_ipa`

`looks_like_ipa(text)` is a heuristic guard, not a classifier. It returns
`True` when the text contains a character *distinctive* to IPA — from the IPA
Extensions, Spacing Modifier Letters, or Phonetic Extensions blocks, or an IPA
combining diacritic:

```python
looks_like_ipa("pʰɑtʃ")   # True
looks_like_ipa("ˈhɛloʊ")  # True
looks_like_ipa("hello")   # False — no distinctive marker
```

A transcription written only with characters IPA shares with the Latin
alphabet (`"pat"`, `"bad"`) has no distinctive marker and returns `False` —
those are the same codepoints as ordinary text, so no function can prove they
are IPA. Use it to *guard* against feeding IPA where orthography is expected,
not to prove a string is not IPA. (This is also why IPA is not a distinct
script: it borrows codepoints from Latin, Greek, and the modifier blocks —
`char_script("ɑ")` is `Latn`, `char_script("θ")` is `Grek`.)
