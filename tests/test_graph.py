import sys
import unittest
from unittest import mock

from scriptconv.graph import (
    DEFAULT_GRAPH,
    REPRESENTATIONS,
    ConversionGraph,
    Edge,
    Representation,
)
from scriptconv.notation import Notation, can_convert, convert


class TestEngine(unittest.TestCase):
    def test_identity_is_empty_route(self):
        g = ConversionGraph([Edge("a", "b", lambda t, **_: t + "b")])
        self.assertEqual(g.route("a", "a"), [])
        self.assertEqual(g.convert("x", "a", "a"), "x")

    def test_multi_hop_route_and_convert(self):
        g = ConversionGraph([
            Edge("a", "b", lambda t, **_: t + ">b", lossless=True),
            Edge("b", "c", lambda t, **_: t + ">c", lossless=True),
        ])
        self.assertEqual([e.dst for e in g.route("a", "c")], ["b", "c"])
        self.assertEqual(g.convert("x", "a", "c"), "x>b>c")

    def test_lossless_two_hop_beats_lossy_direct(self):
        g = ConversionGraph([
            Edge("a", "c", lambda t, **_: "LOSSY"),
            Edge("a", "b", lambda t, **_: t + ">b", lossless=True),
            Edge("b", "c", lambda t, **_: t + ">c", lossless=True),
        ])
        self.assertEqual(g.convert("x", "a", "c"), "x>b>c")

    def test_unroutable_names_reachable_targets(self):
        g = ConversionGraph([Edge("a", "b", lambda t, **_: t, lossless=True)])
        with self.assertRaises(ValueError) as ctx:
            g.route("a", "z")
        self.assertIn("reachable from 'a': b", str(ctx.exception))

    def test_context_passes_through_opaquely(self):
        seen = {}

        def edge_fn(text, **context):
            seen.update(context)
            return text

        g = ConversionGraph([Edge("a", "b", edge_fn)])
        g.convert("x", "a", "b", lang="pt-PT", phoneme_type="espeak")
        self.assertEqual(seen, {"lang": "pt-PT", "phoneme_type": "espeak"})

    def test_copy_and_extend_are_isolated(self):
        g = ConversionGraph([Edge("a", "b", lambda t, **_: t)])
        g2 = g.extend(lambda gg: gg.register(Edge("b", "c", lambda t, **_: t)))
        self.assertTrue(g2.can_convert("a", "c"))
        self.assertFalse(g.can_convert("a", "c"))

    def test_cost_defaults_from_lossless(self):
        self.assertEqual(Edge("a", "b", lambda t, **_: t, lossless=True).cost, 1.0)
        self.assertGreater(Edge("a", "b", lambda t, **_: t).cost, 1.0)
        self.assertEqual(Edge("a", "b", lambda t, **_: t, cost=3.5).cost, 3.5)


class TestNotationParity(unittest.TestCase):
    def test_every_supported_notation_pair_routes_and_matches(self):
        samples = {"ipa": "həˈloʊ", "arpa": "HH AH0 L OW1"}
        for src in Notation:
            for dst in Notation:
                if src == dst:
                    continue
                graph_ok = DEFAULT_GRAPH.can_convert(src.value, dst.value)
                self.assertEqual(can_convert(src, dst), graph_ok,
                                 f"{src}->{dst}")
                if graph_ok and src.value in samples:
                    self.assertEqual(
                        convert(samples[src.value], src, dst),
                        DEFAULT_GRAPH.convert(samples[src.value],
                                              src.value, dst.value))

    def test_buckwalter_not_ipa_routable(self):
        self.assertFalse(DEFAULT_GRAPH.can_convert("buckwalter", "ipa"))
        self.assertTrue(DEFAULT_GRAPH.can_convert("buckwalter", "arabic"))


class TestDefaultGraphOrthography(unittest.TestCase):
    def test_hira_kana_edges(self):
        self.assertEqual(DEFAULT_GRAPH.convert("こんにちは", "hira", "kana"),
                         "コンニチハ")
        self.assertEqual(DEFAULT_GRAPH.convert("コーヒー", "kana", "hira"),
                         "こーひー")

    def test_hangul_to_jamo(self):
        self.assertEqual(DEFAULT_GRAPH.convert("가", "hangul", "jamo"), "ㄱㅏ")

    def test_hanzi_to_cangjie(self):
        self.assertEqual(DEFAULT_GRAPH.convert("日", "hanzi", "cangjie"), "a")

    def test_japanese_readings_edges(self):
        self.assertEqual(DEFAULT_GRAPH.convert("東京", "japanese", "hira"),
                         "とうきょう")
        self.assertEqual(DEFAULT_GRAPH.convert("中国", "hanzi", "pinyin"),
                         "zhōng guó")

    def test_requires_metadata_and_import_hint(self):
        ja_edges = [e for e in DEFAULT_GRAPH.edges
                    if e.src == "japanese" and e.dst == "hira"]
        self.assertEqual(ja_edges[0].requires, "ja")
        import scriptconv.readings as readings
        with mock.patch.object(readings, "_kakasi", None), \
                mock.patch.dict(sys.modules, {"pykakasi": None}):
            with self.assertRaises(ImportError) as ctx:
                DEFAULT_GRAPH.convert("東京", "japanese", "hira")
            self.assertIn("scriptconv[ja]", str(ctx.exception))

    def test_representations_cover_all_default_nodes(self):
        for node in DEFAULT_GRAPH.nodes:
            self.assertIn(node, REPRESENTATIONS, node)

    def test_no_graphemes_node(self):
        self.assertNotIn("graphemes", REPRESENTATIONS)
        self.assertNotIn("graphemes", DEFAULT_GRAPH.nodes)

    def test_representation_kinds(self):
        self.assertEqual(REPRESENTATIONS["ipa"].kind, "notation")
        self.assertEqual(REPRESENTATIONS["pinyin"].system, "pinyin")
        self.assertEqual(REPRESENTATIONS["cangjie"].script, "Hani")


if __name__ == "__main__":
    unittest.main()
