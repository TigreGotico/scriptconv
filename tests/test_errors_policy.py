import json
import pathlib
import unittest

from scriptconv import UnknownSymbolError, convert
from scriptconv import notation as N

FIXTURE = json.loads(
    (pathlib.Path(__file__).parent / "data_errors_fixture.json").read_text())

# (converter name, a sample containing an unknown symbol, the unknown symbol)
UNKNOWN_SAMPLES = [
    ("arpa_to_ipa", "ZZZ", "ZZZ"),
    ("ipa_to_arpa", "χ", "χ"),
    ("xsampa_to_ipa", "¤", "¤"),
    ("ipa_to_xsampa", "¤", "¤"),
    ("lexique_to_ipa", "¤", "¤"),
    ("ipa_to_lexique", "χ", "χ"),
    ("kirshenbaum_to_ipa", "¤", "¤"),
    ("ipa_to_kirshenbaum", "ꟼ", "ꟼ"),
    ("cotovia_to_ipa", "¤", "¤"),
    ("ipa_to_cotovia", "χ", "χ"),
    ("rfe_to_ipa", "¤", "¤"),
    ("ipa_to_rfe", "χ", "χ"),
    ("buckwalter_to_arabic", "#", "#"),
    ("arabic_to_buckwalter", "x", "x"),
]


class TestDefaultsUnchanged(unittest.TestCase):
    """Pre-change fixture battery: no-kwargs output is byte-identical."""

    def test_fixture_battery(self):
        for fn_name, cases in FIXTURE.items():
            fn = getattr(N, fn_name)
            for inp, expected in cases.items():
                self.assertEqual(fn(inp), expected, f"{fn_name}({inp!r})")


class TestPolicies(unittest.TestCase):
    def test_all_four_policies_per_converter(self):
        for fn_name, sample, symbol in UNKNOWN_SAMPLES:
            fn = getattr(N, fn_name)
            passed = fn(sample, errors="pass")
            self.assertIn(symbol, passed, fn_name)
            replaced = fn(sample, errors="replace")
            self.assertNotIn(symbol, replaced, fn_name)
            self.assertIn("?", replaced, fn_name)
            ignored = fn(sample, errors="ignore")
            self.assertNotIn(symbol, ignored, fn_name)
            self.assertNotIn("?", ignored, fn_name)
            with self.assertRaises(UnknownSymbolError, msg=fn_name):
                fn(sample, errors="strict")

    def test_strict_error_names_symbol_position_notation(self):
        with self.assertRaises(UnknownSymbolError) as ctx:
            N.xsampa_to_ipa("ab¤", errors="strict")
        e = ctx.exception
        self.assertEqual(e.symbol, "¤")
        self.assertEqual(e.position, 2)
        self.assertEqual(e.notation, "x-sampa")
        self.assertIn("'¤'", str(e))
        self.assertIn("2", str(e))
        self.assertIn("x-sampa", str(e))

    def test_invalid_policy_raises_value_error(self):
        with self.assertRaises(ValueError):
            N.xsampa_to_ipa("¤", errors="explode")

    def test_unknown_symbol_error_is_value_error(self):
        self.assertTrue(issubclass(UnknownSymbolError, ValueError))


class TestIpaToArpaCompat(unittest.TestCase):
    def test_default_still_replaces_with_question_mark(self):
        self.assertEqual(N.ipa_to_arpa("χ"), "?")

    def test_unknown_empty_still_drops(self):
        self.assertEqual(N.ipa_to_arpa("χkæt", unknown=""), "K AE T")

    def test_custom_unknown_token(self):
        self.assertEqual(N.ipa_to_arpa("χ", unknown="<UNK>"), "<UNK>")

    def test_diacritics_never_treated_as_unknown(self):
        # combining marks qualify the preceding phoneme even under strict
        self.assertEqual(N.ipa_to_arpa("kæ̃t", errors="strict"), "K AE T")


class TestConvertFacade(unittest.TestCase):
    def test_errors_threads_through_routing(self):
        with self.assertRaises(UnknownSymbolError):
            convert("¤", "x-sampa", "arpa", errors="strict")
        self.assertEqual(convert("h@loU", "x-sampa", "arpa"), "HH AX L OW")

    def test_errors_ignore_through_two_hops(self):
        out = convert("k{t¤", "x-sampa", "arpa", errors="ignore")
        self.assertNotIn("¤", out)
        self.assertNotIn("?", out)


if __name__ == "__main__":
    unittest.main()
