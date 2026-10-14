"""The Matoub Kabyle route: it phonemizes, and it is not the africa-g2p route."""
import ast
import pathlib
import sys
import tempfile
import unittest

from scriptconv.phonemizers import ber as _ber_module
from scriptconv.phonemizers._vendored import matoub_kab as _vendored_module
from scriptconv.phonemizers.ber import MatoubKabylePhonemizer
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY, get_phonemizer

_VENDORED = pathlib.Path(_vendored_module.__file__)
_BER = pathlib.Path(_ber_module.__file__)


def _import_roots(path):
    """Root module of every import statement in *path*.

    Relative imports are skipped: they cannot reach outside the package.
    """
    roots = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def _tmp_module(source):
    handle = tempfile.NamedTemporaryFile("w", suffix=".py", delete=False,
                                         encoding="utf-8")
    with handle:
        handle.write(source)
    return pathlib.Path(handle.name)


# Measured against the reference rules in agbalu/Matoub-82M
# tokenization_matoub.py at revision 3d00056f, on 2026-09-25.
REFERENCE = {
    "taddart": "θædːærθ",
    "ameqqran": "æməqːræn",
    "azul fell awen": "æzul fəlː æwən",
    "tamurt n leqbayel": "θæmurθ n ləqβæjəl",
    "aqcic yecca aɣrum": "ɑqʃiʃ jəʃːæ ɑʁrum",
}


class TestMatoubKabyle(unittest.TestCase):
    def setUp(self):
        self.p = MatoubKabylePhonemizer()

    def test_phonemizes_real_words(self):
        for text, expected in REFERENCE.items():
            with self.subTest(text=text):
                self.assertEqual(self.p.phonemize_string(text, "kab"), expected)

    def test_the_rules_that_make_this_route_its_own(self):
        # Each assertion is one rule africa-g2p does not apply. If these ever
        # start matching africa-g2p, the two routes have been conflated.
        # spirantisation: t -> θ, b -> β, d -> ð
        self.assertEqual(self.p.phonemize_string("tamurt", "kab"), "θæmurθ")
        # gemination is length on the restored stop, not a doubled symbol
        self.assertEqual(self.p.phonemize_string("taddart", "kab"), "θædːærθ")
        self.assertNotIn("ðð", self.p.phonemize_string("taddart", "kab"))
        # /a/ backs to ɑ beside a backing consonant, and stays æ otherwise
        self.assertTrue(self.p.phonemize_string("aqcic", "kab").startswith("ɑ"))
        self.assertTrue(self.p.phonemize_string("azul", "kab").startswith("æ"))

    def test_registry_entry_resolves(self):
        self.assertIn(Phonemizer.MATOUB_KAB, PHONEMIZER_REGISTRY)
        module, name, extra = PHONEMIZER_REGISTRY[Phonemizer.MATOUB_KAB]
        self.assertEqual(name, "MatoubKabylePhonemizer")
        # no extra: the rules are vendored and need only the standard library
        self.assertIsNone(extra)
        self.assertIsInstance(get_phonemizer(Phonemizer.MATOUB_KAB),
                              MatoubKabylePhonemizer)

    def test_emits_ipa_and_chunks(self):
        self.assertEqual(self.p.alphabet, Alphabet.IPA)
        self.assertEqual(self.p.phonemize("azul", "kab"), [["æ", "z", "u", "l"]])

    def test_only_kabyle(self):
        self.assertEqual(MatoubKabylePhonemizer.supported_langs(), ["kab"])
        for other in ("eng", "fra", "ber"):
            with self.subTest(lang=other):
                with self.assertRaises(ValueError):
                    self.p.phonemize_string("azul", other)

    def test_an_unknown_character_raises_and_is_never_dropped(self):
        # The upstream file records that silent deletion cost three Kabyle
        # consonants once. A symbol with no rule must be reported.
        with self.assertRaises(ValueError):
            self.p.phonemize_string("aβc", "kab")

    def test_the_vendored_rules_need_no_third_party_import(self):
        # Read the property off the source, not off sys.modules. An earlier
        # form of this test asserted that "transformers" and "torch" were
        # absent from sys.modules; neither is installed, so the assertion was
        # true before the module was imported at all, and adding
        # `import packaging` to the vendored file left it passing.
        #
        # The property is load-bearing: it is why the registry row carries
        # extra=None, and why the rules are vendored instead of depended on. A
        # convenience import added later would keep get_phonemizer working on
        # the machine that added it and fail as an ImportError on a user
        # install.
        for path in (_VENDORED, _BER):
            with self.subTest(path=path.name):
                for root in _import_roots(path):
                    self.assertTrue(
                        root in sys.stdlib_module_names or root == "scriptconv",
                        f"{path.name} imports {root!r}, which is neither the "
                        f"standard library nor scriptconv itself; the registry "
                        f"row advertises this backend as needing no extra")

    def test_that_import_check_fails_on_a_planted_third_party_import(self):
        # The control. Without it the check above could be vacuous for a new
        # reason: a parser that collects nothing also reports nothing.
        planted = _tmp_module("import packaging\nimport re\n")
        self.assertEqual(_import_roots(planted), {"packaging", "re"})
        self.assertNotIn("packaging", sys.stdlib_module_names)
        # and a clean module yields only allowed roots
        clean = _tmp_module("import re\nfrom typing import Final\n")
        self.assertEqual(_import_roots(clean), {"re", "typing"})

    def test_the_import_reader_sees_the_real_files(self):
        # A reader that silently found no imports would make the check above
        # pass for the wrong reason, so pin what it actually collects.
        self.assertIn("re", _import_roots(_VENDORED))
        self.assertIn("scriptconv", _import_roots(_BER))


if __name__ == "__main__":
    unittest.main()
