# scriptconv.translit

Script-level decomposition utilities.

```python
from scriptconv.translit import decompose_hangul
```

---

## decompose_hangul

```python
def decompose_hangul(text: str) -> str
```

Decomposes Hangul syllable block characters into their constituent jamo letters.
Non-Hangul characters pass through unchanged.

```python
decompose_hangul("한국어")   # "ㅎㅏㄴㄱㅜㄱㅇㅓ"
decompose_hangul("값")      # "ㄱㅏㅄ"   (double coda preserved as written)
decompose_hangul("가")      # "ㄱㅏ"     (no coda — empty string omitted)
decompose_hangul("hello 한 world")  # "hello ㅎㅏㄴ world"
decompose_hangul("")        # ""
```

### Unicode arithmetic

Hangul syllable blocks occupy U+AC00–U+D7A3. Each code point encodes an onset jamo,
a vowel jamo, and a (possibly null) coda jamo via the formula:

```
index  = codepoint − 0xAC00
onset  = ONSETS[index // 588]
vowel  = VOWELS[(index % 588) // 28]
coda   = CODAS[index % 28]
```

There are 19 onsets, 21 vowels, and 28 coda slots (index 0 = no coda; indices 1–27
= the 27 coda jamo, including compound codas such as `ㅄ` = *bs*).

### Jamo tables

**Onsets** (19, index 0–18):
`ㄱ ㄲ ㄴ ㄷ ㄸ ㄹ ㅁ ㅂ ㅃ ㅅ ㅆ ㅇ ㅈ ㅉ ㅊ ㅋ ㅌ ㅍ ㅎ`

**Vowels** (21, index 0–20):
`ㅏ ㅐ ㅑ ㅒ ㅓ ㅔ ㅕ ㅖ ㅗ ㅘ ㅙ ㅚ ㅛ ㅜ ㅝ ㅞ ㅟ ㅠ ㅡ ㅢ ㅣ`

**Codas** (28 slots; slot 0 is empty string, slots 1–27 are jamo):
`"" ㄱ ㄲ ㄳ ㄴ ㄵ ㄶ ㄷ ㄹ ㄺ ㄻ ㄼ ㄽ ㄾ ㄿ ㅀ ㅁ ㅂ ㅄ ㅅ ㅆ ㅇ ㅈ ㅊ ㅋ ㅌ ㅍ ㅎ`

### Scope boundary — what decompose_hangul deliberately does NOT do

`decompose_hangul` is an **orthographic** operation. It reflects the written form of
each syllable block and applies no sound rules. Korean phonology involves many
contextual processes that alter how coda consonants are realised when followed by
certain onsets:

| Phonological process | Example | Written jamo | Phonological IPA |
|---------------------|---------|-------------|-----------------|
| Nasal assimilation | 국민 | ㄱㅜㄱ·ㅁㅣㄴ | \[ɡuŋmin\] |
| Coda neutralisation | 낮 | ㄴㅏㅈ | \[nat̚\] |
| Aspiration | 입학 | ㅇㅣㅂ·ㅎㅏㄱ | \[ipʰak\] |
| Resyllabification | 음악 | ㅇㅡㅁ·ㅇㅏㄱ | \[ɯmak\] |

`decompose_hangul` returns the orthographic jamo sequence. For 국민 it returns
`ㄱㅜㄱㅁㅣㄴ` — the written letters — not `ㄱㅜㅇㅁㅣㄴ` (which would reflect the
assimilation). Mapping from jamo to IPA with phonological rules is phonemization and
is outside scriptconv's scope.

Jamo tables derived from [stannam/hangul_to_ipa](https://github.com/stannam/hangul_to_ipa).
