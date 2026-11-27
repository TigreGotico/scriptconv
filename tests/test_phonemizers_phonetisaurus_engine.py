"""The Phonetisaurus wrapper against the REAL engine.

``tests/test_phonemizers_phonetisaurus.py`` stubs ``phonetisaurus.predict``,
so it proves what the wrapper does with an answer and never that the engine
gives one. This file is the other half.

The engine runs from inside the wheel: the binaries and their shared objects
ship with the package, and ``phonetisaurus.guess_environment()`` builds the
``PATH`` and ``LD_LIBRARY_PATH`` that reach them. This file resolves the
binaries the same way, because a binary started with the plain shell
environment exits 127 from the dynamic loader and would make a working box
read as a broken one.

What is not shipped is a model, and scriptconv never downloads. So the cell
SKIPS, with the loader error or the missing model named, unless
``SCRIPTCONV_PHONETISAURUS_MODEL`` points at a trained FST. With one, it
measures two things the stub cannot:

* the wrapper's answer equals ``phonetisaurus-apply``'s own FIRST output line
  for the same word and the same model, and
* ``nbest=2`` returns the same string as ``nbest=1``. ``nbest`` widens the
  search and prints more ranked lines; the wrapper keeps the best one. A
  wrapper that kept the last line would differ here, and the stub suite
  proves that only against a stub.
"""
import os
import shutil
import subprocess
import tempfile
import unittest

MODEL = os.environ.get("SCRIPTCONV_PHONETISAURUS_MODEL")
WORD = os.environ.get("SCRIPTCONV_PHONETISAURUS_WORD", "hello")


def _bin(name, env):
    """Resolve a bundled executable the way the engine does: from the PATH
    ``phonetisaurus.guess_environment`` builds, not the caller's PATH. The
    wheel keeps its binaries inside the package."""
    return shutil.which(name, path=env["PATH"])


def _engine_state():
    """Return None when the engine can run, or the reason it cannot."""
    try:
        import phonetisaurus
    except ImportError as e:
        return f"phonetisaurus is not installed: {e}"
    env = phonetisaurus.guess_environment()
    if not _bin("phonetisaurus-apply", env):
        return "phonetisaurus-apply is not in the package bin directory"
    g2p_bin = _bin("phonetisaurus-g2pfst", env)
    if not g2p_bin:
        return "phonetisaurus-g2pfst is not in the package bin directory"
    # phonetisaurus-apply is a Python script and always starts. The binaries
    # it drives are the ones that fail to load, so probe one of THEM.
    proc = subprocess.run([g2p_bin, "--help"], capture_output=True, text=True,
                          env=env)
    if proc.returncode == 127:
        return (f"phonetisaurus-g2pfst exits 127, the dynamic loader says: "
                f"{proc.stderr.strip() or proc.stdout.strip()}")
    if not MODEL:
        return ("no trained FST: set SCRIPTCONV_PHONETISAURUS_MODEL to a "
                "model path (scriptconv never downloads one)")
    if not os.path.isfile(MODEL):
        return f"SCRIPTCONV_PHONETISAURUS_MODEL is not a file: {MODEL}"
    return None


SKIP_REASON = _engine_state()


def _apply_first_line(word, nbest):
    """The best-ranked pronunciation ``phonetisaurus-apply`` prints itself.

    Its output is one tab-separated line per ranked pronunciation, best
    first. The word is the first field; the rest is the pronunciation.
    """
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
        fh.write(word + "\n")
        word_list = fh.name
    try:
        import phonetisaurus
        env = phonetisaurus.guess_environment()
        proc = subprocess.run(
            [_bin("phonetisaurus-apply", env), "--model", MODEL,
             "--word_list", word_list, "--nbest", str(nbest)],
            capture_output=True, text=True, env=env)
    finally:
        os.unlink(word_list)
    if proc.returncode != 0:
        raise AssertionError(
            f"phonetisaurus-apply exited {proc.returncode}: {proc.stderr}")
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines, f"phonetisaurus-apply printed nothing for {word!r}"
    fields = lines[0].split("\t")
    return " ".join(fields[1:]).split()


@unittest.skipIf(SKIP_REASON is not None, SKIP_REASON or "")
class TestPhonetisaurusRealEngine(unittest.TestCase):

    def _wrapper(self, nbest):
        from scriptconv.phonemizers.enums import Alphabet
        from scriptconv.phonemizers.mul import PhonetisaurusPhonemizer
        return PhonetisaurusPhonemizer(model=MODEL, alphabet=Alphabet.ARPA,
                                       nbest=nbest)

    def test_nbest_1_matches_the_engines_own_first_line(self):
        expected = " ".join(_apply_first_line(WORD, 1))
        self.assertEqual(self._wrapper(1).phonemize_string(WORD, "en"),
                         expected)

    def test_nbest_2_returns_the_same_best_answer_as_nbest_1(self):
        one = self._wrapper(1).phonemize_string(WORD, "en")
        two = self._wrapper(2).phonemize_string(WORD, "en")
        self.assertTrue(one)
        self.assertEqual(one, two)

    def test_nbest_2_makes_the_engine_rank_more_than_one_reading(self):
        # The proof that nbest reached the engine at all: two ranked lines
        # where nbest=1 gives one. A model with a single reading for the word
        # cannot show this, so the cell states that instead of failing.
        import phonetisaurus
        pairs = list(phonetisaurus.predict([WORD], MODEL, nbest=2))
        if len(pairs) < 2:
            self.skipTest(f"the model ranks one reading only for {WORD!r}")
        self.assertEqual({p[0] for p in pairs}, {WORD})


class TestEngineCellIsOwed(unittest.TestCase):
    """This one always runs: it records WHY the cell above did not."""

    def test_the_skip_reason_is_reported(self):
        if SKIP_REASON is None:
            return
        self.assertTrue(SKIP_REASON.strip())
        print(f"\nphonetisaurus real-engine cell skipped: {SKIP_REASON}")
