"""The g2pen backend reads NLTK data from disk and never downloads it.

The fakes below hold the two layouts that NLTK uses for the tagger. They also
model the check that g2p_en 2.1.0 runs at import: it looks for the two zip
resources and calls ``nltk.download`` when either is absent. A build must fail
before that import rather than let the engine start a download.
"""
import sys
import types
import unittest
from unittest.mock import patch

from scriptconv.phonemizers.base import ModelUnavailableError
from scriptconv.phonemizers.en import G2PEnPhonemizer

NEW_DATA = (
    "taggers/averaged_perceptron_tagger.zip",
    "taggers/averaged_perceptron_tagger_eng/",
    "corpora/cmudict.zip",
    "corpora/cmudict",
)
OLD_DATA = (
    "taggers/averaged_perceptron_tagger.zip",
    "taggers/averaged_perceptron_tagger/averaged_perceptron_tagger.pickle",
    "corpora/cmudict.zip",
    "corpora/cmudict",
)
NEW_ZIP_ONLY_DATA = (
    "taggers/averaged_perceptron_tagger.zip",
    "taggers/averaged_perceptron_tagger_eng/",
    "corpora/cmudict.zip",
)
OLD_ZIP_ONLY_DATA = (
    "taggers/averaged_perceptron_tagger.zip",
    "taggers/averaged_perceptron_tagger/averaged_perceptron_tagger.pickle",
    "corpora/cmudict.zip",
)


def _fake_modules(present=(), pickle=None):
    """Fakes for nltk and g2p_en, with a recorder for each call."""
    calls = {"download": [], "find": [], "built": []}

    def find(path):
        calls["find"].append(path)
        if path not in present:
            raise LookupError(f"Resource {path} not found")
        return f"/data/{path}"

    nltk = types.ModuleType("nltk")
    nltk.data = types.SimpleNamespace(find=find)

    def download(*args, **kwargs):
        calls["download"].append(args)

    nltk.download = download

    perceptron = types.ModuleType("nltk.tag.perceptron")
    if pickle is not None:
        perceptron.PICKLE = pickle
    tag = types.ModuleType("nltk.tag")
    tag.perceptron = perceptron
    nltk.tag = tag

    g2p_en = types.ModuleType("g2p_en")

    class G2p:
        def __init__(self):
            calls["built"].append(1)
            for path in ("taggers/averaged_perceptron_tagger.zip", "corpora/cmudict.zip"):
                try:
                    find(path)
                except LookupError:
                    download(path.rsplit("/", 1)[-1].split(".")[0])

        def __call__(self, text):
            return ["HH", "AH", "L", "OW"]

    g2p_en.G2p = G2p
    modules = {"nltk": nltk, "nltk.tag": tag, "nltk.tag.perceptron": perceptron, "g2p_en": g2p_en}
    return calls, modules


class TestG2penReadsLocalNltkData(unittest.TestCase):
    def test_two_builds_never_download(self):
        calls, modules = _fake_modules(NEW_DATA)
        with patch.dict(sys.modules, modules):
            G2PEnPhonemizer()
            G2PEnPhonemizer()
        self.assertEqual(calls["download"], [], "a build called nltk.download")
        self.assertEqual(calls["built"], [1, 1])

    def test_old_nltk_layout_builds_without_download(self):
        calls, modules = _fake_modules(OLD_DATA, pickle="averaged_perceptron_tagger.pickle")
        with patch.dict(sys.modules, modules):
            G2PEnPhonemizer()
        self.assertEqual(calls["download"], [])
        self.assertEqual(calls["built"], [1])

    def test_cmudict_zip_without_a_bare_directory_builds(self):
        for present, pickle in ((NEW_ZIP_ONLY_DATA, None),
                                (OLD_ZIP_ONLY_DATA, "averaged_perceptron_tagger.pickle")):
            with self.subTest(layout=pickle):
                calls, modules = _fake_modules(present, pickle=pickle)
                with patch.dict(sys.modules, modules):
                    G2PEnPhonemizer()
                self.assertEqual(calls["download"], [])
                self.assertEqual(calls["built"], [1])

    def test_missing_data_names_the_install_command(self):
        calls, modules = _fake_modules()
        with patch.dict(sys.modules, modules):
            with self.assertRaises(ModelUnavailableError) as ctx:
                G2PEnPhonemizer()
        message = str(ctx.exception)
        self.assertIn("python -m nltk.downloader", message)
        for package in ("averaged_perceptron_tagger", "averaged_perceptron_tagger_eng", "cmudict"):
            self.assertIn(package, message)
        self.assertEqual(calls["download"], [])
        self.assertEqual(calls["built"], [])

    def test_new_data_without_engine_zips_stops_before_the_engine(self):
        present = ("taggers/averaged_perceptron_tagger_eng/", "corpora/cmudict")
        calls, modules = _fake_modules(present)
        with patch.dict(sys.modules, modules):
            with self.assertRaises(ModelUnavailableError) as ctx:
                G2PEnPhonemizer()
        message = str(ctx.exception)
        self.assertIn("averaged_perceptron_tagger.zip", message)
        self.assertIn("corpora/cmudict.zip", message)
        self.assertEqual(calls["download"], [])
        self.assertEqual(calls["built"], [])

    def test_old_layout_names_only_the_old_tagger_package(self):
        present = tuple(path for path in OLD_DATA if "averaged_perceptron_tagger.pickle" not in path)
        calls, modules = _fake_modules(present, pickle="averaged_perceptron_tagger.pickle")
        with patch.dict(sys.modules, modules):
            with self.assertRaises(ModelUnavailableError) as ctx:
                G2PEnPhonemizer()
        message = str(ctx.exception)
        self.assertIn("averaged_perceptron_tagger", message)
        self.assertNotIn("averaged_perceptron_tagger_eng", message)
        self.assertEqual(calls["download"], [])
        self.assertEqual(calls["built"], [])


if __name__ == "__main__":
    unittest.main()
