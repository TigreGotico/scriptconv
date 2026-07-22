import sys
import types
import unittest
from unittest import mock

from scriptconv.graph import DEFAULT_GRAPH
from scriptconv import diacritics, phonemizers


class TestDiacriticsGraphExtension(unittest.TestCase):
    def setUp(self):
        self.graph = DEFAULT_GRAPH.extend(diacritics.register).extend(phonemizers.register)

    def test_default_graph_has_no_diacritized_node(self):
        self.assertFalse(DEFAULT_GRAPH.can_convert("text", "text-diacritized"))

    def test_extend_adds_diacritized_node(self):
        self.assertTrue(self.graph.can_convert("text", "text-diacritized"))
        self.assertTrue(self.graph.can_convert("text-diacritized", "ipa"))

    def test_text_to_ipa_prefers_direct_route(self):
        route = self.graph.route("text", "ipa")
        self.assertEqual(len(route), 1)
        edge = route[0]
        self.assertEqual(edge.src, "text")
        self.assertEqual(edge.dst, "ipa")

    def test_portuguese_diacritization_via_graph(self):
        out = self.graph.convert("Tenho muita sede hoje.", "text",
                                  "text-diacritized", lang="pt")
        self.assertEqual(out, "Tenho muita sêde hoje.")
        out2 = self.graph.convert("A sede da empresa fica em Lisboa.", "text",
                                   "text-diacritized", lang="pt")
        self.assertEqual(out2, "A séde da empresa fica em Lisboa.")

    def test_slavic_diacritization_routes_to_stressonnx_stub(self):
        calls = []
        mod = types.ModuleType("stressonnx")

        def stress(text, lang, model=None):
            calls.append((text, lang, model))
            return "STRESSED"

        mod.stress = stress
        with mock.patch.dict(sys.modules, {"stressonnx": mod}):
            out = self.graph.convert("замок стоит", "text",
                                      "text-diacritized", lang="ru")
        self.assertEqual(out, "STRESSED")
        self.assertEqual(calls, [("замок стоит", "ru", None)])


if __name__ == "__main__":
    unittest.main()
