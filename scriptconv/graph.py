"""Conversion graph — one routing engine for every text representation.

Nodes are *representations*: phoneme notations ("ipa", "arpa") and
orthographies ("hira", "hanzi", "cangjie") are peers in one flat id
namespace, described by :class:`Representation` metadata.  Edges are
registered transforms between two representations.  Routing finds the
cheapest edge path, preferring lossless edges — silent lossy multi-hop is
the classic failure mode of conversion graphs, so losing information costs
extra by construction.

The engine is generic and dependency-free.  :data:`DEFAULT_GRAPH` comes
pre-registered with scriptconv's own edges: every notation pair (the IPA-hub
routing that :func:`scriptconv.notation.convert` exposes) and the
orthographic conversions from :mod:`translit`, :mod:`cangjie` and
:mod:`readings` (the latter behind their optional extras — the edge exists,
and raises :class:`ImportError` with an install hint when traversed without
the dictionary installed).

External packages extend graphs explicitly — ``pkg.register(graph)`` on a
:meth:`ConversionGraph.copy` or the default graph; there is no entry-point
autoloading, so a graph's contents never depend on what happens to be
installed.  This is also the purity boundary: scriptconv's own edges are
orthography only, but a client (e.g. a TTS stack) may register phonemization
edges into *its* graph instance — the engine routes them without knowing.

Two deliberate non-nodes: "graphemes" (a per-language contextual alias the
caller must resolve — which script a language ordinarily writes in is not a
property of text) and convention styles (:mod:`scriptconv.conventions` —
decorations are parameters of a representation, never nodes, or the graph
would double per style).
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

__all__ = ["Representation", "Edge", "ConversionGraph", "DEFAULT_GRAPH",
           "REPRESENTATIONS"]

_LOSSY_COST = 10.0


@dataclass(frozen=True)
class Representation:
    """Metadata for one node of the conversion space."""
    id: str
    kind: str                      # "notation" | "orthography"
    script: Optional[str] = None   # ISO-15924, when script-bound
    system: Optional[str] = None   # sub-script system ("pinyin", "japanese")
    reference: str = ""


@dataclass(frozen=True)
class Edge:
    """One registered transform between two representations.

    ``fn`` is called as ``fn(text, **context)``; context keys (``lang``,
    engine-specific options…) pass through the router opaquely.  ``requires``
    names an optional extra the transform needs — metadata only; the
    transform itself raises :class:`ImportError` with an install hint.
    ``cost`` defaults from ``lossless`` so routing prefers lossless paths.
    """
    src: str
    dst: str
    fn: Callable[..., str]
    lossless: bool = False
    requires: Optional[str] = None
    cost: float = field(default=-1.0)

    def __post_init__(self):
        if self.cost < 0:
            object.__setattr__(self, "cost",
                               1.0 if self.lossless else _LOSSY_COST)


class ConversionGraph:
    """A registry of edges plus cheapest-path routing between representations."""

    def __init__(self, edges: Optional[List[Edge]] = None):
        self._edges: Dict[str, List[Edge]] = {}
        for e in edges or []:
            self.register(e)

    def register(self, edge: Edge) -> None:
        """Add an edge. A later edge for the same (src, dst) pair wins routing
        only if cheaper; both remain queryable via :attr:`edges`."""
        self._edges.setdefault(edge.src, []).append(edge)

    @property
    def edges(self) -> List[Edge]:
        return [e for outs in self._edges.values() for e in outs]

    @property
    def nodes(self) -> List[str]:
        seen = {e.src for e in self.edges} | {e.dst for e in self.edges}
        return sorted(seen)

    def copy(self) -> "ConversionGraph":
        """Independent copy — registrations on it never affect this graph."""
        return ConversionGraph(self.edges)

    def extend(self, register_fn: Callable[["ConversionGraph"], None]) -> "ConversionGraph":
        """Return a copy extended by *register_fn* (explicit, no autoloading)."""
        g = self.copy()
        register_fn(g)
        return g

    def route(self, src: str, dst: str) -> List[Edge]:
        """Cheapest edge path from *src* to *dst* (empty when src == dst).

        Raises :class:`ValueError` when unroutable, naming the reachable
        targets so callers can self-diagnose.
        """
        if src == dst:
            return []
        best: Dict[str, float] = {src: 0.0}
        back: Dict[str, Edge] = {}
        queue: List[Tuple[float, str]] = [(0.0, src)]
        while queue:
            cost, node = heapq.heappop(queue)
            if node == dst:
                break
            if cost > best.get(node, float("inf")):
                continue
            for e in self._edges.get(node, ()):
                nxt = cost + e.cost
                if nxt < best.get(e.dst, float("inf")):
                    best[e.dst] = nxt
                    back[e.dst] = e
                    heapq.heappush(queue, (nxt, e.dst))
        if dst not in back:
            reachable = sorted(n for n in best if n != src)
            raise ValueError(
                f"no conversion path {src!r} -> {dst!r}; "
                f"reachable from {src!r}: {', '.join(reachable) or '(nothing)'}")
        path: List[Edge] = []
        node = dst
        while node != src:
            edge = back[node]
            path.append(edge)
            node = edge.src
        return list(reversed(path))

    def can_convert(self, src: str, dst: str) -> bool:
        if src == dst:
            return True
        try:
            self.route(src, dst)
            return True
        except ValueError:
            return False

    def convert(self, text: str, src: str, dst: str, **context) -> str:
        """Convert *text* along the cheapest path; context passes through."""
        for edge in self.route(src, dst):
            text = edge.fn(text, **context)
        return text


# ---------------------------------------------------------------------------
# Representation registry and the default graph
# ---------------------------------------------------------------------------

REPRESENTATIONS: Dict[str, Representation] = {r.id: r for r in (
    Representation("ipa", "notation", reference="International Phonetic Alphabet"),
    Representation("arpa", "notation", reference="ARPABET"),
    Representation("x-sampa", "notation", reference="X-SAMPA"),
    Representation("lexique", "notation", reference="Lexique 383"),
    Representation("kirshenbaum", "notation", reference="Kirshenbaum ASCII-IPA"),
    Representation("cotovia", "notation", reference="Cotovía (Galician TTS)"),
    Representation("rfe", "notation", reference="Revista de Filología Española"),
    Representation("buckwalter", "notation", script="Latn",
                   reference="Buckwalter Arabic transliteration"),
    Representation("arabic", "orthography", script="Arab",
                   reference="Arabic script"),
    Representation("japanese", "orthography", script="Jpan", system="japanese",
                   reference="ordinary mixed Japanese orthography (kanji+kana)"),
    Representation("hira", "orthography", script="Hira", reference="Hiragana"),
    Representation("kana", "orthography", script="Kana", reference="Katakana"),
    Representation("hangul", "orthography", script="Hang",
                   reference="Hangul syllable blocks"),
    Representation("jamo", "orthography", script="Hang",
                   reference="decomposed jamo (form is the jamo-form convention)"),
    Representation("hanzi", "orthography", script="Hani",
                   reference="Chinese characters"),
    Representation("cangjie", "orthography", script="Hani",
                   reference="Cangjie5 input codes (glyph shape)"),
    Representation("pinyin", "orthography", script="Latn", system="pinyin",
                   reference="Hanyu Pinyin romanization"),
    Representation("bopomofo", "orthography", script="Bopo",
                   reference="Zhuyin fuhao"),
)}


def _notation_edges() -> List[Edge]:
    from scriptconv.notation import (_TO_IPA, _FROM_IPA, _DIRECT_PAIRS,
                                     NOTATION_INFO)
    edges = []
    def _wrap(fn):
        # forward only the errors= policy from routing context; other context
        # keys (lang, engine options) are not the notation layer's business
        def _edge(text, errors=None, **_):
            return fn(text, errors=errors) if errors is not None else fn(text)
        return _edge

    for notation, fn in _TO_IPA.items():
        info = NOTATION_INFO[notation]
        edges.append(Edge(notation.value, "ipa", _wrap(fn),
                          lossless=info.lossless_to_ipa))
    for notation, fn in _FROM_IPA.items():
        info = NOTATION_INFO[notation]
        edges.append(Edge("ipa", notation.value, _wrap(fn),
                          lossless=info.lossless_from_ipa))
    for (src, dst), fn in _DIRECT_PAIRS.items():
        edges.append(Edge(src.value, dst.value, _wrap(fn), lossless=True))
    return edges


def _orthography_edges() -> List[Edge]:
    def hira_to_kana(text, **_):
        from scriptconv.translit import hira_to_kana as f
        return f(text)

    def kana_to_hira(text, **_):
        from scriptconv.translit import kana_to_hira as f
        return f(text)

    def hangul_to_jamo(text, **_):
        from scriptconv.translit import decompose_hangul
        return decompose_hangul(text)

    def japanese_to_hira(text, **_):
        from scriptconv.readings import to_hiragana
        return to_hiragana(text)

    def japanese_to_kana(text, **_):
        from scriptconv.readings import to_katakana
        return to_katakana(text)

    def hanzi_to_pinyin(text, **_):
        from scriptconv.readings import to_pinyin
        return to_pinyin(text)

    def hanzi_to_bopomofo(text, **_):
        from scriptconv.readings import to_bopomofo
        return to_bopomofo(text)

    def hanzi_to_cangjie(text, **_):
        from scriptconv.cangjie import to_cangjie
        return to_cangjie(text)

    return [
        Edge("hira", "kana", hira_to_kana, lossless=True),
        Edge("kana", "hira", kana_to_hira, lossless=True),
        Edge("hangul", "jamo", hangul_to_jamo, lossless=False),
        Edge("japanese", "hira", japanese_to_hira, requires="ja"),
        Edge("japanese", "kana", japanese_to_kana, requires="ja"),
        Edge("hanzi", "pinyin", hanzi_to_pinyin, requires="zh"),
        Edge("hanzi", "bopomofo", hanzi_to_bopomofo, requires="zh"),
        Edge("hanzi", "cangjie", hanzi_to_cangjie),
    ]


DEFAULT_GRAPH = ConversionGraph(_notation_edges() + _orthography_edges())
