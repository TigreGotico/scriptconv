# scriptconv.scripts

Writing-system identification and metadata.

```python
from scriptconv.scripts import (
    Script, SCRIPT_REGISTRY,
    char_script, detect_script,
    lang_to_script, normalize_script_tag,
)
```

---

## Script dataclass

```python
@dataclass(frozen=True)
class Script:
    iso15924: str                          # Four-letter ISO-15924 code, e.g. "Latn"
    name: str                              # English name, e.g. "Latin"
    direction: str                         # "ltr" or "rtl"
    char_ranges: Tuple[Tuple[int, int], ...]  # Inclusive Unicode codepoint ranges
```

`Script` instances are **frozen** (immutable). Any attempt to assign an attribute raises
`TypeError` or `AttributeError`.

---

## SCRIPT_REGISTRY

`SCRIPT_REGISTRY: dict[str, Script]` — maps ISO-15924 codes to `Script` objects.
The registry covers 31 scripts:

| ISO-15924 | Name | Direction | Unicode ranges (hex, inclusive) |
|-----------|------|-----------|--------------------------------|
| `Arab` | Arabic | rtl | 0600–06FF, 0750–077F, FB50–FDFF, FE70–FEFF |
| `Armn` | Armenian | ltr | 0530–058F |
| `Beng` | Bengali | ltr | 0980–09FF |
| `Cans` | Unified Canadian Aboriginal Syllabics | ltr | 1400–167F, 18B0–18FF |
| `Cprt` | Cypriot | rtl | 10800–1083F |
| `Cyrl` | Cyrillic | ltr | 0400–04FF, 0500–052F |
| `Deva` | Devanagari | ltr | 0900–097F |
| `Ethi` | Ethiopic | ltr | 1200–137F, 1380–139F |
| `Geor` | Georgian | ltr | 10A0–10FF |
| `Glag` | Glagolitic | ltr | 2C00–2C5F |
| `Grek` | Greek | ltr | 0370–03FF, 1F00–1FFF |
| `Gujr` | Gujarati | ltr | 0A80–0AFF |
| `Guru` | Gurmukhi | ltr | 0A00–0A7F |
| `Hang` | Hangul | ltr | AC00–D7AF, 1100–11FF, 3130–318F |
| `Hani` | Han | ltr | 4E00–9FFF, 3400–4DBF, 20000–2A6DF |
| `Hebr` | Hebrew | rtl | 0590–05FF, FB1D–FB4F |
| `Hira` | Hiragana | ltr | 3040–309F |
| `Kana` | Katakana | ltr | 30A0–30FF |
| `Khmr` | Khmer | ltr | 1780–17FF |
| `Laoo` | Lao | ltr | 0E80–0EFF |
| `Latn` | Latin | ltr | 0041–005A, 0061–007A, 00C0–024F |
| `Mymr` | Myanmar | ltr | 1000–109F |
| `Ogam` | Ogham | ltr | 1680–169F |
| `Phnx` | Phoenician | rtl | 10900–1091F |
| `Runr` | Runic | ltr | 16A0–16FF |
| `Sinh` | Sinhala | ltr | 0D80–0DFF |
| `Taml` | Tamil | ltr | 0B80–0BFF |
| `Telu` | Telugu | ltr | 0C00–0C7F |
| `Tfng` | Tifinagh | ltr | 2D30–2D7F |
| `Thai` | Thai | ltr | 0E00–0E7F |
| `Tibt` | Tibetan | ltr | 0F00–0FFF |

---

## char_script

```python
def char_script(ch: str) -> Optional[str]
```

Returns the ISO-15924 code for a single character, or `None` if the character is not in
any registered script's codepoint ranges. ASCII digits (0–9), spaces, and most punctuation
return `None`.

```python
char_script("A")   # "Latn"
char_script("α")   # "Grek"
char_script("가")  # "Hang"
char_script(" ")   # None
char_script("1")   # None
```

**Implementation**: iterates `SCRIPT_REGISTRY` and checks every `(lo, hi)` range for the
character's codepoint. Order of iteration is insertion order (Python 3.7+).

**Gotcha**: characters in overlapping Unicode ranges (very rare in this registry) will
match whichever script appears first in `SCRIPT_REGISTRY`. There are no overlaps in the
current 31-script registry.

---

## detect_script

```python
def detect_script(text: str) -> Optional[str]
```

Returns the ISO-15924 code of the **dominant script** in `text`.

**Algorithm**:
1. For every character, call `char_script`. Skip characters that return `None` (digits,
   spaces, punctuation, symbols outside any registered range).
2. Count how many characters belong to each script.
3. Return the script with the highest count (`max` with count as key).
4. If no script-bearing characters were found (empty string, all digits/punctuation),
   return `None`.

```python
detect_script("Hello world")          # "Latn"
detect_script("Привет мир")           # "Cyrl"
detect_script("مرحبا")               # "Arab"
detect_script("안녕하세요")            # "Hang"
detect_script("Hello Привет мир")    # "Cyrl"  (6 Cyrillic > 5 Latin)
detect_script("")                     # None
detect_script("123 !!!")             # None
```

**Mixed-script behaviour**: returns whichever script has more characters. Ties are broken
by the arbitrary iteration order of the internal count dict; do not rely on tie-breaking
behaviour.

**Gotcha — Japanese**: Japanese text typically mixes Hiragana (`Hira`), Katakana (`Kana`),
and Han (`Hani`). `detect_script` returns the single dominant code; for Japanese NLP,
inspect the full character distribution rather than the single dominant result.

---

## lang_to_script

```python
def lang_to_script(lang: str) -> Optional[str]
```

Returns the ISO-15924 code of the **default writing system** for a language.

`lang` may be a BCP-47 tag (`"pt-BR"`, `"ru-RU"`) or a bare ISO 639 code (`"ru"`). Only
the primary subtag is used (everything up to the first `-` or `_`). The lookup is
case-insensitive on the primary subtag.

Returns `None` for unknown languages.

### Language table (full)

| Code | Language | Script | | Code | Language | Script |
|------|----------|--------|-|------|----------|--------|
| `af` | Afrikaans | Latn | | `lo` | Lao | Laoo |
| `am` | Amharic | Ethi | | `lt` | Lithuanian | Latn |
| `ar` | Arabic | Arab | | `lv` | Latvian | Latn |
| `as` | Assamese | Beng | | `mk` | Macedonian | Cyrl |
| `ast` | Asturian | Latn | | `mn` | Mongolian | Cyrl |
| `av` | Avar | Cyrl | | `mr` | Marathi | Deva |
| `az` | Azerbaijani | Latn | | `ms` | Malay | Latn |
| `ba` | Bashkir | Cyrl | | `mt` | Maltese | Latn |
| `be` | Belarusian | Cyrl | | `mwl` | Mirandese | Latn |
| `bg` | Bulgarian | Cyrl | | `my` | Burmese/Myanmar | Mymr |
| `bn` | Bengali | Beng | | `ne` | Nepali | Deva |
| `bo` | Tibetan | Tibt | | `nl` | Dutch | Latn |
| `br` | Breton | Latn | | `no` | Norwegian | Latn |
| `bxr` | Buryat | Cyrl | | `oc` | Occitan | Latn |
| `ca` | Catalan | Latn | | `om` | Oromo | Latn |
| `ce` | Chechen | Cyrl | | `os` | Ossetian | Cyrl |
| `crk` | Plains Cree | Cans | | `pa` | Punjabi | Guru |
| `cs` | Czech | Latn | | `pl` | Polish | Latn |
| `cv` | Chuvash | Cyrl | | `ps` | Pashto | Arab |
| `cy` | Welsh | Latn | | `pt` | Portuguese | Latn |
| `da` | Danish | Latn | | `ro` | Romanian | Latn |
| `de` | German | Latn | | `ru` | Russian | Cyrl |
| `el` | Greek | Grek | | `rw` | Kinyarwanda | Latn |
| `en` | English | Latn | | `sa` | Sanskrit | Deva |
| `eo` | Esperanto | Latn | | `sah` | Sakha/Yakut | Cyrl |
| `es` | Spanish | Latn | | `sd` | Sindhi | Arab |
| `et` | Estonian | Latn | | `shi` | Tachelhit | Tfng |
| `eu` | Basque | Latn | | `si` | Sinhala | Sinh |
| `fa` | Persian | Arab | | `sk` | Slovak | Latn |
| `fi` | Finnish | Latn | | `sl` | Slovenian | Latn |
| `fo` | Faroese | Latn | | `so` | Somali | Latn |
| `fr` | French | Latn | | `sq` | Albanian | Latn |
| `ga` | Irish | Latn | | `sr` | Serbian | Cyrl |
| `gl` | Galician | Latn | | `sv` | Swedish | Latn |
| `gu` | Gujarati | Gujr | | `sw` | Swahili | Latn |
| `ha` | Hausa | Latn | | `ta` | Tamil | Taml |
| `he` | Hebrew | Hebr | | `te` | Telugu | Telu |
| `hi` | Hindi | Deva | | `tg` | Tajik | Cyrl |
| `hr` | Croatian | Latn | | `th` | Thai | Thai |
| `hu` | Hungarian | Latn | | `ti` | Tigrinya | Ethi |
| `hy` | Armenian | Armn | | `tk` | Turkmen | Latn |
| `id` | Indonesian | Latn | | `tl` | Tagalog | Latn |
| `ig` | Igbo | Latn | | `tr` | Turkish | Latn |
| `is` | Icelandic | Latn | | `tt` | Tatar | Cyrl |
| `it` | Italian | Latn | | `tzm` | Central Atlas Tamazight | Tfng |
| `ja` | Japanese | Hira | | `udm` | Udmurt | Cyrl |
| `ka` | Georgian | Geor | | `ug` | Uyghur | Arab |
| `kk` | Kazakh | Cyrl | | `uk` | Ukrainian | Cyrl |
| `km` | Khmer | Khmr | | `ur` | Urdu | Arab |
| `ko` | Korean | Hang | | `uz` | Uzbek | Latn |
| `kok` | Konkani | Deva | | `vi` | Vietnamese | Latn |
| `ku` | Kurdish | Arab | | `xh` | Xhosa | Latn |
| `ky` | Kyrgyz | Cyrl | | `yue` | Cantonese | Hani |
| `la` | Latin | Latn | | `yi` | Yiddish | Hebr |
| `lb` | Luxembourgish | Latn | | `yo` | Yoruba | Latn |
| `lv` | Latvian | Latn | | `zh` | Chinese | Hani |
|      |          |      | | `zu` | Zulu | Latn |

**Notes**:
- Japanese (`ja`) maps to `Hira` (Hiragana) because Hiragana is the base syllabary.
  Real Japanese text is mixed; use `detect_script` on actual text when the script
  distribution matters.
- Plains Cree (`crk`) maps to `Cans` (Canadian Aboriginal Syllabics), the default
  orthography used in MMS-style labelling (`"syllabics"`).
- Several languages have multiple recognised orthographies; the table records the
  modern standard. Serbian (`sr`) maps to `Cyrl`; Latin-script Serbian is `sr-Latn` —
  `lang_to_script` uses only the primary subtag and will return `Cyrl` for both.

---

## normalize_script_tag

```python
def normalize_script_tag(label: str) -> Optional[str]
```

Maps a free-form script label to its ISO-15924 code. Returns `None` for unrecognised
input.

Accepts:
- MMS-style labels: `"latin"`, `"cyrillic"`, `"arabic"`, `"syllabics"`, `"tifinagh"`,
  `"devanagari"`, `"ethiopic"`, `"khmer"`, `"telugu"`
- Common English names: `"Hebrew"`, `"Hangul"`, `"Korean"`, `"Hiragana"`, `"Katakana"`,
  `"Han"`, `"Hanzi"`, `"Chinese"`, `"Kanji"`, `"Greek"`, `"Armenian"`, `"Georgian"`,
  `"Thai"`, `"Bengali"`, `"Gurmukhi"`, `"Gujarati"`, `"Tamil"`, `"Sinhala"`,
  `"Myanmar"`, `"Burmese"`, `"Tibetan"`, `"Lao"`, `"Glagolitic"`, `"Runic"`,
  `"Ogham"`, `"Phoenician"`, `"CANS"`, `"Unified Canadian Aboriginal Syllabics"`,
  `"Canadian Syllabics"`
- ISO-15924 codes in any case: `"Latn"`, `"latn"`, `"LATN"` → `"Latn"`

```python
normalize_script_tag("latin")      # "Latn"
normalize_script_tag("Cyrillic")   # "Cyrl"
normalize_script_tag("syllabics")  # "Cans"
normalize_script_tag("Korean")     # "Hang"
normalize_script_tag("latn")       # "Latn"
normalize_script_tag("Latn")       # "Latn"
normalize_script_tag("lao")        # "Laoo"   ← label "lao" maps to code "Laoo"
normalize_script_tag("unknown")    # None
```

**Gotcha — "lao" vs "Laoo"**: the English name `"lao"` maps to ISO-15924 `"Laoo"`.
Passing the ISO code `"laoo"` (lowercase) also works via the code-normalisation path.

**Gotcha — case**: lookup is case-insensitive for both the label map and the ISO code
map. `"LATIN"` → lowercased to `"latin"` → found in label map → `"Latn"`.
