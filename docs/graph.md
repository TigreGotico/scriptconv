# The conversion graph — `scriptconv.graph`

Once you have more than a handful of representations, pairwise converters
stop scaling: with nine notations and a dozen orthographies, the interesting
conversions are the ones nobody wrote a direct table for. The graph solves
this once. Every representation is a **node**; every converter is an
**edge**; a conversion request is a **routing problem**.

```python
from scriptconv import DEFAULT_GRAPH

DEFAULT_GRAPH.convert("こんにちは", "hira", "kana")     # 'コンニチハ'
DEFAULT_GRAPH.convert("mrHbaa", "mantoq", "x-sampa")   # via IPA, two hops

[f"{e.src}->{e.dst}" for e in DEFAULT_GRAPH.route("arpa", "x-sampa")]
# ['arpa->ipa', 'ipa->x-sampa']
```

## Nodes: representations

A node is a `Representation(id, kind, script, system, reference)` — notations
(`ipa`, `arpa`, `mantoq`, …) and orthographies (`hira`, `hanzi`, `cangjie`,
`hangul`, `jamo`, …) are peers in one flat id namespace. The `system` field
qualifies sub-script systems (`pinyin` is written in Latin script but is not
"Latin text"), so metadata never overclaims.

Two things are deliberately **not** nodes:

- **"graphemes"** — which script a language ordinarily writes in is a
  property of the *language*, not of text, so a universal "plain text" node
  would have no character-evident identity. The caller resolves it (the
  `phonemizers` extension adds a lang-contextual `text` node to graphs that
  opt in — see below).
- **Convention styles** — decorated and undecorated spellings are the same
  representation; [conventions](conventions.md) handles them as parameters.

## Edges and routing

An `Edge(src, dst, fn, lossless, requires, cost)` wraps a converter with the
metadata routing needs. Edge functions have the signature
`fn(text, **context)`: routing context (`lang=`, `errors=`, engine options)
passes through opaquely — the engine never interprets it.

Routing is cheapest-path with **lossless edges preferred by construction**:
a lossy edge costs an order of magnitude more than a lossless one, so a
lossless two-hop route beats a lossy direct shortcut. Silent lossy multi-hop
is the classic failure mode of conversion graphs; here losing information is
expensive by definition. Unroutable pairs raise a `ValueError` naming the
targets that *are* reachable, so callers can self-diagnose:

```python
DEFAULT_GRAPH.can_convert("buckwalter", "ipa")   # False — transliteration, not phonemes
DEFAULT_GRAPH.route("ipa", "hangul")             # ValueError: reachable from 'ipa': arpa, cotovia, ...
```

## Extension is explicit

`DEFAULT_GRAPH` ships with scriptconv's own edges: every notation pair and
the orthographic conversions. It never grows implicitly — a graph's contents
must not depend on what happens to be installed, so there is no entry-point
autoloading. Extension is a function call that returns a new graph:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import phonemizers

g = DEFAULT_GRAPH.extend(phonemizers.register)   # DEFAULT_GRAPH is untouched
g.convert("bom dia", "text", "ipa", lang="pt")   # 'ˈbõ ˈdʒiɐ'
g.can_convert("text", "arpa")                    # True — phonemize, then transcode
```

`phonemizers.register` is the in-house example of the pattern: it adds the
`text` node (meaningful only with `lang=` context, present only in graphs
that opted in) and one dispatching phonemization edge. Any external package
can do the same with its own `register(graph)`.

`diacritics.register` is a second in-house example: it adds a lang-contextual
`text-diacritized` node and one `text -> text-diacritized` edge (Arabic
tashkeel, Hebrew niqqud, East-Slavic/Turkic/Caucasian stress, European-
Portuguese sense marks). Routing `text -> ipa` is unchanged — the direct
phonemization edge still wins, so stacking this extension is non-invasive:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import diacritics, phonemizers

g = DEFAULT_GRAPH.extend(diacritics.register).extend(phonemizers.register)
g.convert("Tenho muita sede hoje.", "text", "text-diacritized", lang="pt")
# 'Tenho muita sêde hoje.'
g.route("text", "ipa")   # still the single direct edge — no detour
```

The same boundary in one sentence: **scriptconv's own edges are orthography
and notation only; clients may register sound-producing edges into their own
graph instances, and the engine routes them without knowing the difference.**

## CLI

```bash
python -m scriptconv convert hira kana "こんにちは"     # any representation pair
python -m scriptconv route mantoq x-sampa              # show the chosen path
#   mantoq -> ipa  (lossy, cost 10)
#   ipa -> x-sampa  (lossless, cost 1)
```
