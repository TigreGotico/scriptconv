# Dictionary-backed respelling, `scriptconv.readings`

<!-- agent-hint
covers: kanji to kana, the token stream, and hanzi to pinyin or bopomofo
source: scriptconv/readings.py, and the Japanese functions in scriptconv-copyleft
generated: no
verify: python scripts/check_doc_page.py docs/readings.md
see: docs/conventions.md for the wakachigaki and pinyin-tone conventions
-->

This page shows the respellings that need a dictionary: kanji to kana, and
hanzi to pinyin or bopomofo.

Some respellings are mechanical: katakana is hiragana shifted by a fixed
codepoint offset, and a Hangul syllable decomposes into jamo by arithmetic.
Those live in [translit](translit.md). This module handles the respellings
that are **lexical**: how a kanji is written in kana, or a hanzi in pinyin,
is a property of the *word*, resolved against a reading dictionary, with
genuinely ambiguous cases decided by that dictionary's segmentation. The
output is still orthography, exactly what an IME or furigana would render,
never phonology: no sound rules are applied.

Because dictionaries are heavyweight, the module's backends are optional
extras. Importing the module is always safe, the dependency resolves on
first conversion, and a missing dictionary raises `ImportError` with the
install command rather than silently returning unconverted text.

## Japanese, kanji → kana (`pip install scriptconv[ja]`)

The Japanese functions wrap pykakasi, which is GPL-3.0-or-later, so they are
in the scriptconv-copyleft package. The `ja` extra installs it, and the names
below import from it on first use.

```python
from scriptconv import to_hiragana, to_katakana

to_hiragana("東京タワー")                     # 'とうきょうたわー'
to_hiragana("コーヒー", keep_katakana=True)   # 'コーヒー'   (loanwords keep their script)
to_katakana("日本語")                         # 'ニホンゴ'
to_hiragana("私は学生です", segment=True)     # 'わたし は がくせい です'  (wakachigaki)
```

`keep_katakana=True` preserves katakana tokens instead of folding them into
hiragana, useful when katakana deliberately marks loanwords. `segment=True`
joins dictionary tokens with spaces: *wakachigaki*, the spaced orthographic
mode used in children's books and games (its inverse lives in
[conventions](conventions.md) as the `wakachigaki` convention).

### The token stream

`tokens()` is the primitive underneath both functions. It yields one
`ReadingToken(orig, hira, kana)` per dictionary-segmented token, and the
surface forms concatenate back to the input exactly, so consumers that need
word boundaries or reading-dependent post-processing build on it directly
instead of re-parsing a joined string:

```python
from scriptconv import tokens

[t.orig for t in tokens("私はcoffeeが好き")]
# ['私', 'は', 'coffee', 'が', '好き']
```

## Chinese, hanzi → pinyin / bopomofo (`pip install scriptconv[zh]`)

Pinyin and bopomofo (zhuyin) are both kana-like respellings of Chinese:
standard ways of writing the language phonetically. The phrase dictionary
decides heteronyms, the characters with several readings:

```python
from scriptconv import to_pinyin, to_bopomofo

to_pinyin("中国人")               # 'zhōng guó rén'
to_pinyin("银行")                 # 'yín háng'   (行 as in bank)
to_pinyin("行走")                 # 'xíng zǒu'   (行 as in walk)
to_pinyin("中国", tone="number")  # 'zhong1 guo2'
to_bopomofo("中国")               # 'ㄓㄨㄥ ㄍㄨㄛˊ'
```

Syllables are space-separated, pinyin's own orthographic convention. The
`tone=` styles (`"mark"`, `"number"`, `"none"`) are the styles of the
`pinyin-tone` convention, existing pinyin text converts between them without
the `zh` extra via `restyle` (see [conventions](conventions.md)).

## Scope boundary

The line this module holds: a dictionary **lookup** is orthography and
belongs here, contextual **prediction** does not. Restoring Arabic vowel
marks is a modelling problem. `scriptconv.diacritics.diacritize` calls a
model for it behind the `tashkeel` extra, and this module does not.

---
[Index](index.md) · [← translit](translit.md) · [conventions →](conventions.md)
