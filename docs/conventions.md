# Orthographic conventions, `scriptconv.conventions`

<!-- agent-hint
covers: the convention registry and the strip, apply, restyle and detect calls
source: scriptconv/conventions.py
generated: no
verify: python -c '(I:=__import__,ast:=I("ast"),re:=I("re"),sys:=I("sys"),inspect:=I("inspect"),enum:=I("enum"),dataclasses:=I("dataclasses"),unittest:=I("unittest"),f:=sys.argv[1],g:={},T:=unittest.TestCase(),B:=re.findall(r"\x60{3}python\n(.*?)\x60{3}",open(f,encoding="utf-8").read(),re.S),K:=lambda o:[(p.name,p.kind,p.default) for p in inspect.signature(o).parameters.values()] if not isinstance(o,type) else [(m.name,m.value) for m in o] if issubclass(o,enum.Enum) else [x.name for x in dataclasses.fields(o)],D:=lambda b:((s:=re.sub(r"\)( -> .+)?$",r")\1: ...",b.strip()) if b.startswith("def") else b),(h:=dict(g)),exec("from __future__ import annotations\nfrom enum import Enum\nfrom dataclasses import dataclass\n"+s,h),[K(h[d.name])==K(g[d.name]) or (d.name,K(h[d.name]),K(g[d.name])) for d in ast.parse(s).body])[-1],C:=lambda s,L:None if not isinstance(s,ast.Expr) else (m.group(1) if (m:=re.search(r"\s#\s?(.*)$",L[s.end_lineno-1])) else L[s.end_lineno][2:] if s.end_lineno<len(L) and L[s.end_lineno].startswith("# ") else None),X:=lambda s:compile(ast.Expression(s.value),f,"eval"),Q:=lambda s,e:(T.assertRaisesRegex(eval(e.split(":")[0],g),re.escape(e.partition(":")[2].strip()),eval,X(s),g) or True) if re.match(r"\w+Error\b",e) else (True if (v:=eval(X(s),g))==ast.literal_eval(e) else (ast.unparse(s),e,v)),R:=lambda s,L:exec(compile(ast.Module([s],[]),f,"exec"),g) if (c:=C(s,L)) is None else Q(s,c.split("  ")[0].strip()),r:=[y for b in B for y in (D(b) if re.match(r"def |class |@",b) else [R(s,b.splitlines()) for s in ast.parse(b).body]) if y is not None],w:=[y for y in r if y is not True],print("OK",len(r)) if not w else sys.exit("MISMATCH "+repr(w)))' docs/conventions.md
see: docs/graph.md, and scriptconv/diacritics.py for restoring marks
-->

This page shows how to strip, add and restyle the optional marks of a
script, such as Arabic vowel marks or pinyin tones.

Two pieces of Arabic text can be the same words with and without vowel marks.
Japanese can be written solid or with spaces between words. Pinyin writes
tone as diacritics or as digits. None of these differences change what script
the text is in. They are **decorations** a script's orthography can carry or
omit. This module models them as ordinary data, with one uniform algebra
for adding, removing, and restyling them.

The distinction that shapes the whole design: **scripts are identity,
conventions are parameters.** A convention never participates in script
detection and is never a node in the conversion graph. Otherwise every
representation would split into one node per decoration state.

## The algebra

Every convention declares its *styles*, the mutually exclusive states its
text can be in. Binary decorations have styles `("marked", "none")`, variant
conventions name their spellings (`("mark", "number", "none")`). The one real
operation is `restyle`, a transition between styles. Everything else is sugar:

```python
from scriptconv import strip, apply, restyle, detect_convention, conventions_for

strip("مُحَمَّد", "tashkeel")          # 'محمد'         restyle to "none"
restyle("zhong1", "pinyin-tone", "mark")   # 'zhōng'
detect_convention("مُحَمَّد", "tashkeel")   # 'marked'
[c.id for c in conventions_for("Hebr")]   # ['niqqud', 'teamim']
```

Which transitions exist follows one criterion, applied uniformly:

- **Deterministic re-spelling** (stripping marks, converting tone digits to
  diacritics) is always available, zero-dependency.
- **Dictionary lookup** (applying wakachigaki requires word segmentation) is
  in scope but behind an extra, mirroring [readings](readings.md).
- **Contextual prediction** (restoring stripped tashkeel or niqqud) is not a
  convention. That is diacritization, a modelling problem, and it belongs to
  `scriptconv.diacritics`. Its absence here is a queryable fact of the
  registry, not a runtime surprise.

Unsupported transitions raise `ValueError` listing the supported ones. A
transition whose backing extra is missing raises `ImportError` naming it.

## The registry

| id | script(s) | styles | notes |
|---|---|---|---|
| `tashkeel` | Arab | marked/none | harakat, tanwin, shadda, sukun, dagger alef |
| `kashida` | Arab | marked/none | tatweel justification, its own layer, not vocalization |
| `quranic-marks` | Arab | marked/none | annotation signs, structural signs (end-of-ayah) survive |
| `niqqud` | Hebr | marked/none | points incl. dagesh, meteg, rafe, shin/sin dots |
| `teamim` | Hebr | marked/none | cantillation, a separate layer from niqqud |
| `wakachigaki` | Hira, Kana, Hani | marked/none | Japanese word spacing |
| `pinyin-tone` | Latn (pinyin) | mark/number/none | tone spelling styles |
| `jamo-form` | Hang | compatibility/conjoining | Unicode jamo repertoires |

Worked examples across the registry:

```python
strip("שָׁלוֹם", "niqqud")                          # 'שלום'
strip("וַ֑יֹּאמֶר", "teamim")                        # 'וַיֹּאמֶר'  (cantillation gone, vowels kept)
strip("わたし は がくせい です", "wakachigaki")      # 'わたしはがくせいです'
strip("محمـــد", "kashida")                       # 'محمد'
restyle("zhōng guó", "pinyin-tone", "number", frm="mark")   # 'zhong1 guo2'
restyle("ㄱㅏㅁ", "jamo-form", "conjoining")        # '\u1100\u1161\u11b7'  (conjoining jamo, rendered as 감)
```

## Linguistic care baked into the tables

The codepoint sets are curated against real failure modes, not just block
ranges:

- **Tashkeel excludes U+0653-0655** (madda, hamza above, hamza below). In
  decomposed text those combining marks *are* the letters آ / أ / إ. A
  blanket strip corrupts the consonantal skeleton. Decomposed Arabic
  round-trips with its hamzas intact.
- **Niqqud and teamim are separate layers**, as in Masoretic practice. Maqaf
  and sof pasuq are punctuation and survive both strips. Stripping the
  shin/sin dots loses the שׁ/שׂ distinction, exactly as unpointed Hebrew
  does. The registry says so.
- **Wakachigaki stripping is flank-conservative**: a space is removed only
  when *both* neighbors are Japanese characters. "きょうは good day" and
  "第 3 章" keep their spaces, because those spaces carry information.
- **Pinyin tone restyling is deterministic both ways** for standard
  apostrophized pinyin (mark placement follows the a/e-first rule, `ü`
  accepts the `v` and `u:` input spellings, erhua and syllabic nasals like
  `ḿ` are handled). On non-apostrophized input, digit placement is
  best-effort and documented as such.
- **`jamo-form` is a Unicode representation convention** rather than an
  orthographic one, registered because free text genuinely occurs in both
  repertoires, and stated as the registry's one deliberate boundary
  exception. Compatibility jamo don't distinguish onset from coda, so the
  conjoining direction resolves position from context.

What is *not* a convention: marks that are letter identity. Vietnamese tone
diacritics spell different words. Stripping them is corruption, not
undecoration, and no such operation exists here. Casing on bicameral scripts
fits the concept but is already modelled correctly by `str.lower` /
`str.casefold`, so it is deliberately not duplicated.

---
[Index](index.md) · [← readings](readings.md) · [graph →](graph.md)
