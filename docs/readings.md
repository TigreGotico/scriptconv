# Dictionary-backed respelling, `scriptconv.readings`

<!-- agent-hint
covers: kanji to kana, the token stream, and hanzi to pinyin or bopomofo
source: scriptconv/readings.py, and the Japanese functions in scriptconv-copyleft
generated: no
verify: python -c '(I:=__import__,ast:=I("ast"),re:=I("re"),sys:=I("sys"),inspect:=I("inspect"),enum:=I("enum"),dataclasses:=I("dataclasses"),unittest:=I("unittest"),f:=sys.argv[1],g:={},T:=unittest.TestCase(),B:=re.findall(r"\x60{3}python\n(.*?)\x60{3}",open(f,encoding="utf-8").read(),re.S),K:=lambda o:[(p.name,p.kind,p.default) for p in inspect.signature(o).parameters.values()] if not isinstance(o,type) else [(m.name,m.value) for m in o] if issubclass(o,enum.Enum) else [x.name for x in dataclasses.fields(o)],D:=lambda b:((s:=re.sub(r"\)( -> .+)?$",r")\1: ...",b.strip()) if b.startswith("def") else b),(h:=dict(g)),exec("from __future__ import annotations\nfrom enum import Enum\nfrom dataclasses import dataclass\n"+s,h),[K(h[d.name])==K(g[d.name]) or (d.name,K(h[d.name]),K(g[d.name])) for d in ast.parse(s).body])[-1],C:=lambda s,L:None if not isinstance(s,ast.Expr) else (m.group(1) if (m:=re.search(r"\s#\s?(.*)$",L[s.end_lineno-1])) else L[s.end_lineno][2:] if s.end_lineno<len(L) and L[s.end_lineno].startswith("# ") else None),X:=lambda s:compile(ast.Expression(s.value),f,"eval"),Q:=lambda s,e:(T.assertRaisesRegex(eval(e.split(":")[0],g),re.escape(e.partition(":")[2].strip()),eval,X(s),g) or True) if re.match(r"\w+Error\b",e) else (True if (v:=eval(X(s),g))==ast.literal_eval(e) else (ast.unparse(s),e,v)),R:=lambda s,L:exec(compile(ast.Module([s],[]),f,"exec"),g) if (c:=C(s,L)) is None else Q(s,c.split("  ")[0].strip()),r:=[y for b in B for y in (D(b) if re.match(r"def |class |@",b) else [R(s,b.splitlines()) for s in ast.parse(b).body]) if y is not None],w:=[y for y in r if y is not True],print("OK",len(r)) if not w else sys.exit("MISMATCH "+repr(w)))' docs/readings.md
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
