# The conversion graph, `scriptconv.graph`

<!-- agent-hint
covers: nodes, edges, routing, and the opt-in phonemizer and diacritics edges
source: scriptconv/graph.py, `register` in scriptconv/phonemizers/registry.py and scriptconv/diacritics.py
generated: no
verify: python -c '(I:=__import__,ast:=I("ast"),re:=I("re"),sys:=I("sys"),inspect:=I("inspect"),enum:=I("enum"),dataclasses:=I("dataclasses"),unittest:=I("unittest"),f:=sys.argv[1],g:={},T:=unittest.TestCase(),B:=re.findall(r"\x60{3}python\n(.*?)\x60{3}",open(f,encoding="utf-8").read(),re.S),K:=lambda o:[(p.name,p.kind,p.default) for p in inspect.signature(o).parameters.values()] if not isinstance(o,type) else [(m.name,m.value) for m in o] if issubclass(o,enum.Enum) else [x.name for x in dataclasses.fields(o)],D:=lambda b:((s:=re.sub(r"\)( -> .+)?$",r")\1: ...",b.strip()) if b.startswith("def") else b),(h:=dict(g)),exec("from __future__ import annotations\nfrom enum import Enum\nfrom dataclasses import dataclass\n"+s,h),[K(h[d.name])==K(g[d.name]) or (d.name,K(h[d.name]),K(g[d.name])) for d in ast.parse(s).body])[-1],C:=lambda s,L:None if not isinstance(s,ast.Expr) else (m.group(1) if (m:=re.search(r"\s#\s?(.*)$",L[s.end_lineno-1])) else L[s.end_lineno][2:] if s.end_lineno<len(L) and L[s.end_lineno].startswith("# ") else None),X:=lambda s:compile(ast.Expression(s.value),f,"eval"),Q:=lambda s,e:(T.assertRaisesRegex(eval(e.split(":")[0],g),re.escape(e.partition(":")[2].strip()),eval,X(s),g) or True) if re.match(r"\w+Error\b",e) else (True if (v:=eval(X(s),g))==ast.literal_eval(e) else (ast.unparse(s),e,v)),R:=lambda s,L:exec(compile(ast.Module([s],[]),f,"exec"),g) if (c:=C(s,L)) is None else Q(s,c.split("  ")[0].strip()),r:=[y for b in B for y in (D(b) if re.match(r"def |class |@",b) else [R(s,b.splitlines()) for s in ast.parse(b).body]) if y is not None],w:=[y for y in r if y is not True],print("OK",len(r)) if not w else sys.exit("MISMATCH "+repr(w)))' docs/graph.md
see: docs/phonemizers.md, docs/stack.md
-->

This page shows how the conversion graph finds a path between two
representations, and how to add edges to a graph.

Once you have more than a handful of representations, pairwise converters
stop scaling: with nine notations and a dozen orthographies, the interesting
conversions are the ones nobody wrote a direct table for. The graph solves
this once. Every representation is a **node**, every converter is an
**edge**, a conversion request is a **routing problem**.

```python
from scriptconv import DEFAULT_GRAPH

DEFAULT_GRAPH.convert("こんにちは", "hira", "kana")     # 'コンニチハ'
DEFAULT_GRAPH.convert("mrHbaa", "halabi", "x-sampa")   # 'mrX\\ba:'  (through IPA, two hops)

[f"{e.src}->{e.dst}" for e in DEFAULT_GRAPH.route("arpa", "x-sampa")]
# ['arpa->ipa', 'ipa->x-sampa']
```

## Nodes: representations

A node is a `Representation(id, kind, script, system, reference)`, notations
(`ipa`, `arpa`, `halabi`, …) and orthographies (`hira`, `hanzi`, `cangjie`,
`hangul`, `jamo`, …) are peers in one flat id namespace. The `system` field
qualifies sub-script systems (`pinyin` is written in Latin script but is not
"Latin text"), so metadata never overclaims.

Two things are deliberately **not** nodes:

- **"graphemes"**, which script a language ordinarily writes in is a
  property of the *language*, not of text, so a universal "plain text" node
  would have no character-evident identity. The caller resolves it (the
  `phonemizers` extension adds a lang-contextual `text` node to graphs that
  opt in, see below).
- **Convention styles**, decorated and undecorated spellings are the same
  representation, [conventions](conventions.md) handles them as parameters.

## Edges and routing

An `Edge(src, dst, fn, lossless, requires, cost)` wraps a converter with the
metadata routing needs. Edge functions have the signature
`fn(text, **context)`: routing context (`lang=`, `errors=`, engine options)
passes through opaquely, the engine never interprets it.

Routing is cheapest-path with **lossless edges preferred by construction**:
a lossy edge costs an order of magnitude more than a lossless one, so a
lossless two-hop route beats a lossy direct shortcut. Silent lossy multi-hop
is the classic failure mode of conversion graphs, here losing information is
expensive by definition. Unroutable pairs raise a `ValueError` naming the
targets that *are* reachable, so callers can self-diagnose:

```python
DEFAULT_GRAPH.can_convert("buckwalter", "ipa")   # False  (transliteration, not phonemes)
DEFAULT_GRAPH.route("ipa", "hangul")             # ValueError: no conversion path 'ipa' -> 'hangul'  (the message lists the reachable targets)
```

## Extension is explicit

`DEFAULT_GRAPH` ships with scriptconv's own edges: every notation pair and
the orthographic conversions. It never grows implicitly, a graph's contents
must not depend on what happens to be installed, so there is no entry-point
autoloading. Extension is a function call that returns a new graph:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import phonemizers

g = DEFAULT_GRAPH.extend(phonemizers.register)   # DEFAULT_GRAPH is untouched
g.convert("bom dia", "text", "ipa", lang="pt")   # 'ˈbõ ˈdiɐ'
g.can_convert("text", "arpa")                    # True  (phonemize, then transcode)
```

`phonemizers.register` is the in-house example of the pattern: it adds the
`text` node (meaningful only with `lang=` context, present only in graphs
that opted in) and one dispatching phonemization edge. Any external package
can do the same with its own `register(graph)`.

`diacritics.register` is a second in-house example: it adds a lang-contextual
`text-diacritized` node and a pair of edges, `text -> text-diacritized`
(restore: Arabic tashkeel, Hebrew niqqud, East-Slavic/Turkic/Caucasian stress,
European-Portuguese sense marks) and `text-diacritized -> text` (strip).
Restore is model-based and expensive. Strip is cheap, and it is not lossless
either: a letter with a mark and the bare letter strip to one string, so no
reverse returns both. Both edges carry `lossless=False`. Strip removes only the specific overlay codepoints each backend adds (combining
acute/grave for stress, tashkeel for Arabic, niqqud for Hebrew), never a
blanket combining-mark filter, so precomposed native letters (Cyrillic й/ё,
Latvian macrons, Azerbaijani ç/ö, Arabic hamza carriers) survive intact. A
cheapest path never visits a node twice, so routing never takes the round
trip. Strip is also gated, by exact primary-subtag match, to *overlay*
diacritics (Arabic/Hebrew vocalization, East-Slavic/Turkic stress), whose bare
canonical form carries no marks, European Portuguese diacritics are native
orthography, so stripping them would corrupt the spelling (`café` → `cafe`),
and the edge raises `ValueError` for those languages instead. Routing `text -> ipa` is
unchanged either way, the direct phonemization edge still wins, so stacking
this extension is non-invasive:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import diacritics, phonemizers

g = DEFAULT_GRAPH.extend(diacritics.register).extend(phonemizers.register)
g.convert("Tenho muita sede hoje.", "text", "text-diacritized", lang="pt")
# 'Tenho muita sêde hoje.'
g.convert("за́мок", "text-diacritized", "text", lang="ru")   # 'замок'  (strip)
[f"{e.src}->{e.dst}" for e in g.route("text", "ipa")]   # ['text->ipa']  (the single direct edge, no detour)
```

The same boundary in one sentence: **scriptconv's own edges are orthography
and notation only, clients may register sound-producing edges into their own
graph instances, and the engine routes them without knowing the difference.**

## CLI

```bash
python -m scriptconv convert hira kana "こんにちは"     # any representation pair
python -m scriptconv route halabi x-sampa              # show the chosen path
#   halabi -> ipa  (lossy, cost 10)
#   ipa -> x-sampa  (lossless, cost 1)
```

---
[Index](index.md) · [← conventions](conventions.md) · [phonemizers →](phonemizers.md)
