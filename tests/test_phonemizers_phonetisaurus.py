"""The Phonetisaurus wrapper: registry wiring, the model contract, and the
output string.

Phonetisaurus carries no rules of its own. Everything it knows is in one
trained FST, and no FST is published with the ``phonetisaurus`` package or with
scriptconv, so a test that phonemizes a real word against a real model would
have to train one or download one. Training runs the bundled ``estimate-ngram``
binary, which is a system-level dependency this suite must not need, and a test
never downloads. So the engine call is stubbed at the one function the wrapper
uses, ``phonetisaurus.predict``, and the assertions are on the string the
wrapper builds from the engine's answer. The parts NOT stubbed are the parts
this wrapper owns: the model contract, the word indexing, the separator and the
alphabet check.
"""
import os
import sys
import tempfile
import unittest
from types import ModuleType
from unittest.mock import patch

from scriptconv.phonemizers import Phonemizer, get_phonemizer_class
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY


def _fake_phonetisaurus(answers, reorder=True):
    """A stand-in for the ``phonetisaurus`` package, exposing only
    ``predict``, which is the whole surface the wrapper uses.

    The real ``predict`` reads a word list and yields ``(word, symbols)``
    pairs. It does not promise the caller's order, and it yields nothing for a
    word the model cannot read. The stub returns pairs in REVERSE order by
    default for exactly that reason: a wrapper that consumed the pairs
    positionally would pass this suite if the stub echoed the request order,
    and would put the wrong pronunciation on every word in production.

    ``nbest`` is modelled too, because it changes the SHAPE of the answer and
    not just its length: the engine prints one line per ranked pronunciation,
    BEST FIRST, and ``predict`` yields one pair per line, so a word appears
    ``nbest`` times. ``answers`` maps a word to its ranked list, best first.

    The reversal therefore applies to the WORDS and never inside one word's
    ranked lines. Word order is a freedom the engine has; rank order is a
    promise it keeps, and a stub that broke it would be testing a different
    engine.
    """
    mod = ModuleType("phonetisaurus")

    def predict(words, model_path, nbest=1, env=None):
        # one group per word, the group's pairs in rank order
        groups = [[(w, ranked) for ranked in answers[w][:nbest]]
                  for w in words if w in answers]
        if reorder:
            # the WORDS may come back in any order; the ranked lines of one
            # word may not, so the groups reverse and their contents do not
            groups.reverse()
        for group in groups:
            for pair in group:
                yield pair

    mod.predict = predict
    return mod


class TestRegistryWiring(unittest.TestCase):
    def test_registry_names_the_module_class_and_extra(self):
        entry = PHONEMIZER_REGISTRY[Phonemizer.PHONETISAURUS]
        self.assertEqual(
            entry,
            ("scriptconv.phonemizers.mul", "PhonetisaurusPhonemizer",
             "phonetisaurus"))

    def test_the_class_resolves(self):
        cls = get_phonemizer_class(Phonemizer.PHONETISAURUS)
        self.assertEqual(cls.__name__, "PhonetisaurusPhonemizer")

    def test_the_enum_value_is_the_wire_string(self):
        self.assertEqual(Phonemizer.PHONETISAURUS.value, "phonetisaurus")

    def test_the_extra_is_declared_in_pyproject(self):
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(root, "pyproject.toml"), "rb") as f:
            extras = tomllib.load(f)["project"]["optional-dependencies"]
        self.assertIn("phonetisaurus", extras)
        self.assertIn("phonetisaurus", extras["phonetisaurus"])


class TestModelContract(unittest.TestCase):
    """scriptconv never downloads a model, so the wrapper must refuse to be
    built without one, and say what to pass."""

    def _cls(self):
        return get_phonemizer_class(Phonemizer.PHONETISAURUS)

    def test_no_model_is_refused(self):
        with patch.dict(sys.modules,
                        {"phonetisaurus": _fake_phonetisaurus({})}):
            with self.assertRaises(ValueError) as ctx:
                self._cls()()
        self.assertIn("model=", str(ctx.exception))

    def test_a_missing_file_is_refused(self):
        with patch.dict(sys.modules,
                        {"phonetisaurus": _fake_phonetisaurus({})}):
            with self.assertRaises(ValueError):
                self._cls()(model="/nonexistent/g2p.fst")

    def test_an_alphabet_the_wrapper_does_not_declare_is_refused(self):
        with tempfile.NamedTemporaryFile(suffix=".fst") as fst:
            with patch.dict(sys.modules,
                            {"phonetisaurus": _fake_phonetisaurus({})}):
                with self.assertRaises(ValueError) as ctx:
                    self._cls()(model=fst.name, alphabet=Alphabet.HANGUL)
        self.assertIn("hangul", str(ctx.exception))


class TestOutputString(unittest.TestCase):
    """What the wrapper builds out of the engine's answer."""

    def _phonemizer(self, answers, **kw):
        cls = get_phonemizer_class(Phonemizer.PHONETISAURUS)
        fst = tempfile.NamedTemporaryFile(suffix=".fst", delete=False)
        fst.close()
        self.addCleanup(os.unlink, fst.name)
        with patch.dict(sys.modules,
                        {"phonetisaurus": _fake_phonetisaurus(answers)}):
            return cls(model=fst.name, **kw)

    def test_one_word(self):
        p = self._phonemizer({"cat": [["k", "a", "t"]]})
        self.assertEqual(p.phonemize_string("cat", "en"), "k a t")

    def test_two_words_keep_their_order(self):
        p = self._phonemizer({"cat": [["k", "a", "t"]],
                              "bat": [["b", "a", "t"]]})
        self.assertEqual(p.phonemize_string("cat bat", "en"), "k a t b a t")

    def test_an_empty_separator_gives_a_bare_string(self):
        p = self._phonemizer({"cat": [["k", "a", "t"]]}, separator="")
        self.assertEqual(p.phonemize_string("cat", "en"), "kat")

    def test_a_word_the_engine_drops_is_skipped(self):
        """predict() yields nothing for a word the model cannot read. The
        wrapper drops it rather than raising."""
        p = self._phonemizer({"cat": [["k", "a", "t"]],
                              "bat": [["b", "a", "t"]]})
        self.assertEqual(p.phonemize_string("cat xyzzy bat", "en"),
                         "k a t b a t")

    def test_the_output_follows_the_INPUT_order_not_the_engine_order(self):
        """The discriminating case. The stub answers in reverse, so a wrapper
        that consumed the pairs positionally would return them reversed. The
        wrapper indexes by word, so the sentence keeps its own order."""
        p = self._phonemizer({"cat": [["k", "a", "t"]],
                              "dog": [["d", "o", "g"]],
                              "bat": [["b", "a", "t"]]})
        self.assertEqual(p.phonemize_string("cat dog bat", "en"),
                         "k a t d o g b a t")

    def test_nbest_2_keeps_the_BEST_ranked_pronunciation(self):
        """With nbest > 1 the engine yields one pair per ranked reading, best
        first, so a word appears twice. Building a dict over the pairs keeps
        the LAST one, which is the worst-ranked reading, while the docstring
        promises the best. The wrapper keeps the first pair per word.

        This is the case that tells the two apart: both readings are present,
        both are well-formed, and only the ORDER says which is right."""
        p = self._phonemizer({"cat": [["k", "a", "t"], ["k", "a", "ts"]]},
                             nbest=2)
        self.assertEqual(p.phonemize_string("cat", "en"), "k a t")

    def test_nbest_2_over_several_words(self):
        p = self._phonemizer({"cat": [["k", "a", "t"], ["k", "a", "ts"]],
                              "bat": [["b", "a", "t"], ["b", "a", "ts"]]},
                             nbest=2)
        self.assertEqual(p.phonemize_string("cat bat", "en"), "k a t b a t")

    def test_empty_text(self):
        p = self._phonemizer({"cat": [["k", "a", "t"]]})
        self.assertEqual(p.phonemize_string("", "en"), "")

    def test_the_language_argument_does_not_route(self):
        """The model decides the language. Any tag must give the same answer,
        because the wrapper claims no routing."""
        p = self._phonemizer({"cat": [["k", "a", "t"]]})
        self.assertEqual(p.phonemize_string("cat", "en"),
                         p.phonemize_string("cat", "oc"))

    def test_the_declared_alphabet_is_kept(self):
        p = self._phonemizer({"cat": [["K", "AE", "T"]]}, alphabet=Alphabet.ARPA)
        self.assertEqual(p.alphabet, Alphabet.ARPA)
        self.assertEqual(p.phonemize_string("cat", "en"), "K AE T")


if __name__ == "__main__":
    unittest.main()
