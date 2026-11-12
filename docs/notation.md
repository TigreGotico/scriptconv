# scriptconv.notation

Phoneme-notation transcoding. All tables are pure Python data, zero runtime dependencies.

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
convert("S", Notation.XSAMPA, Notation.IPA)  # enum members, equivalent
```

---

## convert, facade

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
because the Buckwalter table maps to script characters, not to IPA phonemes, IPA for
Arabic requires a phonemizer.

```python
convert("NG", "arpa", "x-sampa")   # "N"
convert("Sa", "lexique", "x-sampa")  # "Sa"  (ʃ→S, a→a)
```

**Identity**: `convert(text, x, x)` always returns `text` unchanged.

---

## Unknown symbols, `errors=`

Every converter takes `errors="pass" | "replace" | "strict" | "ignore"` for a symbol
that its table does not map. `"strict"` raises `UnknownSymbolError` with the symbol,
its position and the notation. Strict follows three rules:

1. Strict drops no mark. A diacritic or a modifier letter with no value in the target
   raises. `ipa_to_arpa("kʰæt", errors="strict")` raises on `ʰ`, and the default gives
   `K AE T`.
2. Strict raises on any other symbol that the table does not map.
3. Strict accepts spaces. A space is a character with the Unicode White_Space
   property, 25 code points. Each converter keeps a space under every policy, because a
   space is not an unknown symbol. ARPABET has no word boundary, so `ipa_to_arpa`
   drops the space and `arpa_to_ipa` splits its tokens on it. U+001C to U+001F and
   U+200B are not White_Space, so strict raises on them.

With `stress=False`, `ipa_to_arpa` drops a stress mark under every policy, because
the caller asked for ARPABET with no stress digits.

---

## ARPABET ↔ IPA

Table derived from [chorusai/arpa2ipa](https://github.com/chorusai/arpa2ipa) (Apache-2.0).
Values follow the [CMU Pronouncing Dictionary](http://www.speech.cs.cmu.edu/cgi-bin/cmudict)
phone set and the [ARPABET table](https://en.wikipedia.org/wiki/ARPABET) that dictionary
refers to for IPA. `tests/test_notation_sources.py` quotes both.

### arpa_to_ipa

```python
def arpa_to_ipa(arpa_sequence: str) -> str
```

Converts a space-separated ARPABET token sequence to an IPA string. Stress digits
(`0`, `1`, `2`) are stripped before lookup. Unknown tokens are passed through unchanged.

**Stress digit handling**:
- `AH0` is special-cased: maps to `ə` (schwa), not `ʌ`.
- `AH1`, `AH2` → `ʌ` (stressed vowel).
- `ER0` is special-cased: maps to `ɚ`, not `ɝ`. CMUdict has no `AXR`, so it spells that phone `ER0`.
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
(default `"?"`), pass `unknown=""` to drop them silently. A space has no token and is
dropped, so the output keeps no word boundary: `"ɛ ɛ"` and `"ɛɛ"` both give `EH EH`.
The tied affricates `t͡ʃ` and `d͡ʒ` give `CH` and `JH`, with the tie above or below.

With `stress=True`, a stress mark gives its digit to the next vowel. The IPA puts the
mark before the stressed syllable, so `bəˈnænə` gives `B AH0 N AE1 N AH0`, as in the
CMU Pronouncing Dictionary. A mark before the vowel gives the same result. A stress
mark does not cross a space.

```python
ipa_to_arpa("həloʊ")   # "HH AX L OW"
ipa_to_arpa("ŋ")       # "NG"
ipa_to_arpa("ɸ")       # "?"
ipa_to_arpa("ɸ", unknown="")  # ""
```

**Stress loss**: IPA → ARPABET is lossy for stress. The base ARPABET form (no digit) is
always returned, stress digits cannot be recovered from plain IPA.

**AH0/AX asymmetry**: `AH0` (unstressed `AH`) maps to `ə` in the forward direction, the reverse maps `ə` to `AX` (the CMU `AX` token, which also denotes schwa). This is a
known asymmetry: `arpa_to_ipa("AH0") == "ə"` but `ipa_to_arpa("ə") == "AX"`.

### Round-trip guarantees

ARPA → IPA → ARPA is exact for consonants and for vowels that have a unique IPA
symbol:

```
P → p → P    B → b → B    TH → θ → TH    NG → ŋ → NG (exact)
```

It is **lossy** for:
- Stress digits: `AH1` → `ʌ` → `AH` (digit lost).
- `AH0` → `ə` → `AX` and `ER0` → `ɚ` → `AXR` (token changes).

IPA → ARPA → IPA is also lossy because the reverse table uses base ARPABET forms.

---

## X-SAMPA ↔ IPA

The table follows J.C. Wells, [Computer-coding the IPA: a proposed extension of
SAMPA](https://www.phon.ucl.ac.uk/home/sampa/x-sampa.htm). `tests/test_notation_sources.py`
quotes it row by row and lists each spelling left out, with the reason.

### xsampa_to_ipa

```python
def xsampa_to_ipa(xsampa: str) -> str
```

Converts an X-SAMPA string to IPA. Multi-character symbols are matched **longest-first**
at each position. Unknown characters are passed through unchanged.

**Key multi-character cases** (longest-first matching is required):

| X-SAMPA | IPA | Note |
|---------|-----|------|
| `tS` | `tʃ` | palato-alveolar affricate, must not split as `t` + `S`=`ʃ` |
| `dZ` | `dʒ` | voiced affricate |
| `r\` | `ɹ` | approximant r. Must match before plain `r` |
| *r\\`* | `ɻ` | retroflex approximant. Longest match |
| `@\` | `ɘ` | close-mid central unrounded. Before `@`=`ə` |
| *@\`* | `ɚ` | r-coloured schwa. Before `@` |
| `N\` | `ɴ` | uvular nasal. Before `N`=`ŋ` |
| `G\` | `ɢ` | voiced uvular stop. Before `G`=`ɣ` |

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

IPA → X-SAMPA → IPA is lossless for every symbol Wells lists, each taken alone,
including diacritics and tones. A sequence of symbols can differ, as the tie bar
below shows. `ipa_to_xsampa` decomposes its input first, so precomposed `ã` gives
`a~`. The labiodental flap `ⱱ` joined the IPA later and has no spelling. The syllabic mark
above a letter gives `=`, so `ŋ̍` gives `N=`. The voiceless ring above `ŋ` gives `_0`,
so `ŋ̊` gives `N_0`. Both return with the diacritic below the letter. The IPA moves a
mark above a letter "to avoid a descender or another diacritic". So the ring above
reads as voiceless after a letter with a descender, such as `ɡ̊`, and after a mark below,
such as `ç̊`. A letter has a descender when its glyph reaches more than 0.1 em below the
baseline in both DejaVu Sans and DejaVu Serif. The ring above any other letter stays
unknown, because `å` is a letter of Nordic orthography and not IPA.
The tie bar is `_`, which also opens a diacritic, so `t͡s` gives `t_s` and `t͡θ` gives
`tT`: Wells assumes affricate status where no tie is written, and the tie itself does
not come back. `a͡ɨ` gives `a1` for the same reason, because `_1` is a tone number.
A tone number has no IPA value, so `xsampa_to_ipa` treats each of `_1` to `_6` as one
unknown symbol. The falling tone ``_` `` of Wells's section 24 is one unknown symbol for
the same reason, and not a tie before the rhoticity mark. `a_7`, `a_8` and `a_9` are the tie and a vowel, because the tone numbers
stop at 6.
X-SAMPA → IPA → X-SAMPA is lossless for every spelling Wells lists. A second spelling
returns as the first.

**Second spellings**: Wells gives more than one spelling for a few symbols. The reverse
table emits the first:

| X-SAMPA spellings | IPA | First spelling |
|-------------------|-----|---------------|
| `P` or `v\` | ʋ | `P` |
| `=` or `_=` | ◌̩ | `=` |
| `~` or `_~` | ◌̃ | `~` |
| `'` or `_j` | ʲ | `'` |
| `_R`, `_/` or `_L_H` | ◌̌ | `_R` |
| `_F`, `_\` or `_H_L` | ◌̂ | `_F` |
| `_R_F`, `_M_H_L` or `_/_\` | ◌᷈ | `_R_F` |

```python
ipa_to_xsampa("ʋ")   # "P"  (not "v\\")
ipa_to_xsampa("ã")   # "a~"
```

---

## Buckwalter ↔ Arabic script

Table follows Tim Buckwalter's published Arabic transliteration scheme, a
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
| `{` | ٱ | alef wasla |
| `` ` `` | ٰ | dagger alef |

**Presentation forms**: `arabic_to_buckwalter` also reads the Arabic Presentation
Forms-A and -B. Each takes the spelling of the letters that its NFKC decomposition
gives, so the lam-alef ligature `ﻸ` (U+FEF8) gives `l>`, and returns as `لأ`.

---

## Lexique ↔ IPA

Source: New, B. & Pallier, C., *Manuel de Lexique 3* v3.11, Tableau 2 (p. 12).
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
lexique_to_ipa("aNo")     # "aɲo"    (agneau, N=ɲ palatal nasal)
lexique_to_ipa("kaGiG")   # "kaŋiŋ"  (camping, G=ŋ velar nasal)
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

Lexique → IPA → Lexique is exact except for the `°`/`3` schwa pair (both map to `ə`
in IPA, reverse always produces `°`). All other phonemes round-trip exactly.

---

## can_convert, predicate

```python
def can_convert(src: str | Notation, dst: str | Notation) -> bool
```

Returns `True` if a conversion from *src* to *dst* is supported (direct or indirect
through IPA). Does not perform any conversion.

```python
can_convert("arpa", "ipa")         # True  (direct)
can_convert("arpa", "x-sampa")     # True  (indirect: arpa→ipa→x-sampa)
can_convert("buckwalter", "ipa")   # False (not supported)
can_convert("ipa", "ipa")          # False (identity, use convert() instead)
```

---

## convert_batch, line-by-line generator

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

Each character maps independently, characters outside the table pass through.
Neither direction is lossless. Kirshenbaum → IPA keeps every key under a round trip, but 31 of the 96 keys give output that is not IPA, such as `F`, `K`, `P`, digits and punctuation. `IPA → Kirshenbaum → IPA` is lossy for IPA outside the ASCII inventory.

## Queryable fidelity, `NOTATION_INFO`

The fidelity guarantees are exposed as data so callers can branch on them
instead of reading prose:

```python
from scriptconv import NOTATION_INFO, Notation
info = NOTATION_INFO[Notation.ARPA]
info.lossless_from_ipa   # False, restricted English inventory
info.token_separated     # True (space-separated ARPABET tokens)
info.reference           # citation URL/string
```

Each `NotationInfo` carries `lossless_to_ipa`, `lossless_from_ipa`,
`token_separated`, and `reference`.

The two flags share one definition. A conversion is lossless when it passes this
test for every symbol of its source inventory. Both converters run with
`errors="strict"` and with their other options at the defaults:

1. The symbol converts, and every output symbol is in the target inventory. An
   unmapped symbol passed through does not count, and neither does a table row
   whose output is not in that inventory.
2. The reverse conversion returns the input. Where the notation's reference gives
   two spellings of one symbol, the first spelling counts as the input.

The source inventory of `lossless_to_ipa` is the notation's own symbol set. The
source inventory of `lossless_from_ipa` is the 1993 IPA Chart as X-SAMPA lists it,
each symbol taken alone, so a flag makes no claim about a sequence of symbols. A
notation with no converter in the direction under test is not lossless in that
direction, so Buckwalter, which converts to Arabic script and not to IPA, has both
flags `False`.

The conversion graph gives each IPA edge the flag of its direction. The Buckwalter
and Arabic-script edges pass the same test, so they are lossless too. For them, an
Arabic presentation form is a second spelling of the letters that NFKC gives.

The defaults matter for ARPABET. With `stress=True`, `AH1` returns as `AH1`, but the
graph and the flags use the default `stress=False`, so `lossless_to_ipa` is `False`.

`tests/test_notation_sources.py` measures each flag and both Buckwalter edges against
both clauses. Towards
IPA, the target inventory is the set of IPA symbols in the Wells rows of that file.
ARPABET and X-SAMPA inventories come from their sources. The Lexique, Kirshenbaum,
Cotovía and RFE inventories are the code's own keys, because no source for them is
quoted there. A failure on a key proves a flag `False`, and all four notations hold
`False` in both directions.

## Notation detection, `looks_like_ipa`

`looks_like_ipa(text)` is a heuristic guard, not a classifier. It returns
`True` when the text contains a character *distinctive* to IPA, from the IPA
Extensions, Spacing Modifier Letters, or Phonetic Extensions blocks, or an IPA
combining diacritic:

```python
looks_like_ipa("pʰɑtʃ")   # True
looks_like_ipa("ˈhɛloʊ")  # True
looks_like_ipa("hello")   # False, no distinctive marker
```

A transcription written only with characters IPA shares with the Latin
alphabet (`"pat"`, `"bad"`) has no distinctive marker and returns `False`.
Those are the same codepoints as ordinary text, so no function can prove they
are IPA. Use it to *guard* against feeding IPA where orthography is expected,
not to prove a string is not IPA. (This is also why IPA is not a distinct
script: it borrows codepoints from Latin, Greek, and the modifier blocks.
`char_script("ɑ")` is `Latn`, `char_script("θ")` is `Grek`.)

## Cotovía ↔ IPA

Cotovía is the internal phoneme notation of the Universidade de Vigo GTM
Cotovía TTS system (Galician/Spanish). The table is the phoneme symbol map from
its `fonemas.cpp`, symbols are matched longest-first (`tS`, `rr` before single
characters).

```python
cotovia_to_ipa("tS")      # "tʃ"
cotovia_to_ipa("karro")   # "karo"  (rr = trill r, single r = tap ɾ)
ipa_to_cotovia("ʎ")       # "L"     (canonical palatal-lateral symbol)
```

The silence/pause marker (`#`) is a boundary token, not a phoneme, and is
excluded from the table. Three source symbols (`L`, `Z`, `jj`) map to `ʎ`, the
reverse direction emits the standard Cotovía `L`.


## RFE (Revista de Filología Española) ↔ IPA

The RFE phonetic alphabet (Navarro Tomás, *Revista de Filología Española*,
1915) is the traditional transcription system of Spanish and Romance
philology. scriptconv provides its core, well-attested inventory (rare
interdental and variant diacritic symbols from the full standard are omitted).

```python
rfe_to_ipa("kaša")   # "kaʃa"
ipa_to_rfe("ɲ")      # "ñ"     (canonical, n̮ is also accepted on input)
rfe_to_ipa("far̄a")  # trill r (r̄), single r is the tap ɾ
```

The palatal nasal accepts both `ñ` and `n̮` on input and emits `ñ`, the
tap/trill distinction (`r` = ɾ, `r̄` = r) round-trips exactly.

## ARPABET stress convention (`stress=True`)

Stress digits map to IPA stress marks placed **immediately before the stressed
vowel's symbol**, a purely notational, reversible convention, no
syllabification is performed. Worked examples:

- `HH AH0 L OW1` ↔ `həlˈoʊ` (primary stress on `OW`)
- `K AE1 T` ↔ `kˈæt`
- `P ER0 M IH2 T` ↔ `pɚmˌɪt` (secondary stress on `IH`)

Unmarked vowels round-trip as digit `0`, consonants never carry digits.
Residues (all stable from the IPA side): extended-ARPABET `AX` and `AXR` normalise
to CMUdict's `AH0` and `ER0` spellings, and symbol sequences that concatenate to a
single IPA symbol fuse to it, `T SH` → `CH`, `D ZH` → `JH` (affricates), contiguous IPA carries no token boundary, so this fusion is inherent and
applies in default mode too. The general contract: round-trips are exact up
to IPA-equivalence, a fused spelling always produces the identical IPA.

## Halabi → IPA (Nawar Halabi's Arabic-Phonetiser inventory)

Halabi is the phonetic notation emitted by Nawar Halabi's Arabic-Phonetiser
(the rule engine the `mantoq` package wraps): ASCII consonant letters with
the inventory's own conventions (`^` is θ, `v` a loan phoneme), plain
short/long vowels (`a`/`aa`/`aaaa`), a gemination marker `_dbl_`, a word
separator `_+_`, and `<` for the glottal stop. Published models trained on
this notation make it worth transcoding, so it is a full `Notation` member
with a one-directional converter:

```python
from scriptconv.notation import halabi_to_ipa
from scriptconv import convert, can_convert

halabi_to_ipa("s a l aa m")        # 's a l aː m'
halabi_to_ipa("b_dbl_a")           # 'bːa'      (consonant gemination)
convert("mrHbaa", "halabi", "x-sampa")   # routes halabi → ipa → x-sampa
can_convert("ipa", "halabi")       # False, one-directional by design
```

The inventory's semantics are honoured precisely: `_dbl_` geminates only
consonants (the pipeline never emits it after a vowel), `_sil_` becomes a
pause, `_eos_`/`_pad_` are dropped, and a pre-tokenized sequence (as returned
by the mantoq package's `g2p`) is accepted directly, since joining tokens
into a string is ambiguous. The token → IPA table maps the inventory's
phonetic values; the phonetiser *engine* itself lives in
[phonemizers](phonemizers.md) under its own license.

`halabi_to_ipa` also accepts the RAW (pre-`simplify_phonemes`) phonetiser
output — the emphatic-context uppercase vowels (`A`/`AA`/`I`/`II`/`U`/`UU`)
that `Phonemizer.HALABI` returns natively, since mantoq's own g2p folds them
to the plain forms above before a caller ever sees them.

### `iqra_halabi_to_ipa` — the IqraEval `phoneme_ref` flavor

`Phonemizer.IQRA`'s output uses a related but distinct table: gemination is a
literal doubled consonant letter (`bb`, `nn`, …) rather than a `_dbl_`
marker, and the emphatic-context vowels stay distinct rather than folding to
the plain forms. `scriptconv.notation.iqra_halabi_to_ipa` implements this
table (verified symbol-by-symbol against IqraEval/Iqra_train by
TigreGotico/arbtok's `scripts/benchmark_iqraeval.py`):

```python
from scriptconv.notation import iqra_halabi_to_ipa

iqra_halabi_to_ipa("f ii h i x A y r aa t")   # 'fiːhixɑjraːt'
```

---
[← scripts](scripts.md) · [Home](../README.md) · [translit →](translit.md)
