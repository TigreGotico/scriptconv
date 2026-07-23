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

    def test_strip_recovers_bare_russian(self):
        out = self.graph.convert("за́мок", "text-diacritized", "text", lang="ru")
        self.assertEqual(out, "замок")

    def test_strip_recovers_bare_arabic(self):
        vocalized = "مُحَمَّد"
        bare = "".join(c for c in vocalized if not (0x064B <= ord(c) <= 0x065F
                                                     or ord(c) == 0x0670))
        out = self.graph.convert(vocalized, "text-diacritized", "text", lang="ar")
        self.assertEqual(out, bare)
        self.assertEqual(out, "محمد")

    def test_strip_refused_for_portuguese(self):
        with self.assertRaises(ValueError) as ctx:
            self.graph.convert("sêde", "text-diacritized", "text", lang="pt")
        self.assertIn("native orthography", str(ctx.exception))

    def test_strip_edge_does_not_change_text_to_ipa_route(self):
        route = self.graph.route("text", "ipa")
        self.assertEqual(len(route), 1)
        edge = route[0]
        self.assertEqual(edge.src, "text")
        self.assertEqual(edge.dst, "ipa")

    def test_strip_preserves_cyrillic_native_letters(self):
        out = self.graph.convert("мой родно́й край", "text-diacritized",
                                  "text", lang="ru")
        self.assertEqual(out, "мой родной край")
        out2 = self.graph.convert("ёлка", "text-diacritized", "text", lang="ru")
        self.assertEqual(out2, "ёлка")

    def test_strip_preserves_latin_stress_lang_diacritics(self):
        # native macron (ī) plus an added combining acute overlay
        out = self.graph.convert("Rī́ga", "text-diacritized", "text",
                                  lang="lv")
        self.assertEqual(out, "Rīga")
        out2 = self.graph.convert("Rīga", "text-diacritized", "text", lang="lv")
        self.assertEqual(out2, "Rīga")

    def test_strip_preserves_arabic_hamza(self):
        out = self.graph.convert("أَحْمَد", "text-diacritized", "text", lang="ar")
        self.assertEqual(out, "أحمد")

    def test_strip_refuses_aragonese(self):
        with self.assertRaises(ValueError):
            self.graph.convert("Cristián", "text-diacritized", "text", lang="arg")

    def test_add_diacritics_does_not_misroute_herero(self):
        self.assertEqual(diacritics.diacritize("teste", "her"), "teste")


if __name__ == "__main__":
    unittest.main()
