"""Tests for the Russian (vosk-tts) phonemizer and its vendored G2P rules."""
import os
import tempfile
import unittest

from scriptconv.phonemizers import (
    Alphabet,
    Phonemizer,
    PHONEMIZER_REGISTRY,
    get_phonemizer,
    phonemize,
    phonemizer_for_lang,
)
from scriptconv.phonemizers._thirdparty.vosk_g2p import convert, load_dictionary
from scriptconv.phonemizers.ru import VoskPhonemizer


class TestVoskRules(unittest.TestCase):
    """The vendored rules, exercised directly (no dictionary involved)."""

    def test_palatalization_before_soft_vowel(self):
        # рь/ви soften: r -> rj, v -> vj; unstressed vowels get the 0 digit
        self.assertEqual(convert("привет"), "p rj i0 vj e0 t")

    def test_hard_consonant_before_hard_vowel(self):
        self.assertEqual(convert("как"), "k a0 k")

    def test_plus_marks_the_next_vowel_as_stressed(self):
        self.assertEqual(convert("прив+ет"), "p rj i0 vj e1 t")
        # without the marker every vowel is unstressed
        self.assertEqual(convert("привет"), "p rj i0 vj e0 t")

    def test_stress_marker_only_affects_its_own_vowel(self):
        self.assertEqual(convert("м+олоко"), "m o1 l o0 k o0")
        self.assertEqual(convert("молок+о"), "m o0 l o0 k o1")

    def test_multi_character_phonemes(self):
        # щ -> sch, ш -> sh, ж -> zh, ч -> ch, ц -> c
        self.assertEqual(convert("щука"), "sch u0 k a0")
        self.assertEqual(convert("шар"), "sh a0 r")
        self.assertEqual(convert("жук"), "zh u0 k")
        self.assertEqual(convert("час"), "ch a0 s")
        self.assertEqual(convert("цирк"), "c i0 r k")

    def test_iotated_vowel_gains_a_glide_at_syllable_start(self):
        self.assertEqual(convert("яма"), "j a0 m a0")
        self.assertEqual(convert("ёж"), "j o0 zh")
        # ... but not after a consonant, where it palatalizes instead
        self.assertEqual(convert("тётя"), "tj o0 tj a0")

    def test_soft_and_hard_signs_are_dropped_from_the_stream(self):
        out = convert("съешь")
        self.assertEqual(out, "s j e0 sh")
        self.assertNotIn("ь", out)
        self.assertNotIn("ъ", out)

    def test_empty_word_yields_empty_string(self):
        self.assertEqual(convert(""), "")

    def test_non_cyrillic_passes_through_verbatim(self):
        self.assertEqual(convert("abc"), "a b c")


class TestLoadDictionary(unittest.TestCase):
    def _write(self, content: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".dict")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        self.addCleanup(os.remove, path)
        return path

    def test_missing_path_yields_empty_map(self):
        self.assertEqual(load_dictionary(None), {})
        self.assertEqual(load_dictionary("/nonexistent/vosk/dictionary"), {})

    def test_legacy_layout_word_then_phonemes(self):
        path = self._write("привет p rj i0 vj e1 t\nкак k a1 k\n")
        dic = load_dictionary(path)
        self.assertEqual(dic["привет"], ["p", "rj", "i0", "vj", "e1", "t"])
        self.assertEqual(dic["как"], ["k", "a1", "k"])

    def test_probability_layout_keeps_highest_variant(self):
        path = self._write("что 0.2 ch t o1\nчто 0.8 sh t o1\n")
        self.assertEqual(load_dictionary(path)["что"], ["sh", "t", "o1"])

    def test_legacy_layout_keeps_first_variant(self):
        path = self._write("что ch t o1\nчто sh t o1\n")
        self.assertEqual(load_dictionary(path)["что"], ["ch", "t", "o1"])

    def test_blank_and_short_lines_ignored(self):
        path = self._write("\n\nдом d o1 m\nбезфонем\n   \n")
        dic = load_dictionary(path)
        self.assertEqual(list(dic), ["дом"])


class TestVoskPhonemizer(unittest.TestCase):
    def setUp(self):
        self.p = VoskPhonemizer()

    def test_sentence_string(self):
        self.assertEqual(self.p.phonemize_string("Привет, как дела?", "ru"),
                         "p rj i0 vj e0 t ,   k a0 k   dj e0 l a0 ?")

    def test_case_is_folded(self):
        self.assertEqual(self.p.phonemize_string("ПРИВЕТ", "ru"),
                         self.p.phonemize_string("привет", "ru"))

    def test_punctuation_and_space_survive_as_tokens(self):
        toks = self.p.phonemize_to_list("да, нет!", "ru")
        self.assertIn(",", toks)
        self.assertIn(" ", toks)
        self.assertEqual(toks[-1], "!")

    def test_multi_char_tokens_stay_whole(self):
        # the base class would split "sch" into s/c/h — this backend must not
        self.assertIn("sch", self.p.phonemize_to_list("щука", "ru"))

    def test_em_dash_becomes_a_hyphen_pause(self):
        toks = self.p.phonemize_to_list("Москва — столица", "ru")
        self.assertIn("-", toks)
        self.assertNotIn("—", toks)

    def test_phonemize_returns_one_list_per_sentence(self):
        chunks = self.p.phonemize("Привет. Как дела?", "ru")
        self.assertEqual(len(chunks), 2)
        self.assertTrue(all(isinstance(c, list) for c in chunks))
        self.assertEqual(chunks[0][:3], ["p", "rj", "i0"])

    def test_empty_text_yields_no_chunks(self):
        self.assertEqual(self.p.phonemize("", "ru"), [])
        self.assertEqual(self.p.phonemize_to_list("", "ru"), [])
        self.assertEqual(self.p.phonemize_string("", "ru"), "")

    def test_punctuation_only_input(self):
        self.assertEqual(self.p.phonemize_to_list("...", "ru"), [".", ".", "."])

    def test_non_cyrillic_input_is_not_dropped(self):
        # OOV latin text has no vosk rule; it must survive rather than vanish
        self.assertEqual(self.p.phonemize_string("hello world", "ru"),
                         "h e l l o   w o r l d")

    def test_digits_survive_unnormalized(self):
        # scriptconv performs no normalization of its own
        self.assertIn("3", self.p.phonemize_to_list("3 кота", "ru"))

    def test_normalizer_hook_runs_before_g2p(self):
        p = VoskPhonemizer()
        p.normalizer = lambda t, l: t.replace("3", "три")
        self.assertEqual(p.phonemize("3", "ru"), [["t", "rj", "i0"]])

    def test_rejects_unsupported_language(self):
        with self.assertRaises(ValueError):
            self.p.phonemize_string("hello", "en-US")
        with self.assertRaises(ValueError):
            self.p.phonemize("привет", "zh-CN")

    def test_rejects_non_vosk_alphabet(self):
        with self.assertRaises(ValueError):
            VoskPhonemizer(alphabet=Alphabet.IPA)

    def test_dictionary_overrides_the_rules(self):
        fd, path = tempfile.mkstemp(suffix=".dict")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("привет 1.0 p rj i0 vj e1 t\n")
        self.addCleanup(os.remove, path)
        p = VoskPhonemizer(model=path)
        # e1 (stressed) comes from the dictionary; the rules alone give e0
        self.assertEqual(p.phonemize_string("привет", "ru"),
                         "p rj i0 vj e1 t")
        # an out-of-dictionary word still falls back to the rules
        self.assertEqual(p.phonemize_string("щука", "ru"), "sch u0 k a0")

    def test_missing_dictionary_falls_back_to_rules(self):
        p = VoskPhonemizer(model="/nonexistent/vosk/dictionary")
        self.assertEqual(p.dictionary, {})
        self.assertEqual(p.phonemize_string("привет", "ru"), "p rj i0 vj e0 t")

    def test_dictionary_is_lazy(self):
        p = VoskPhonemizer(model="/nonexistent/vosk/dictionary")
        self.assertIsNone(p._dictionary)
        p.dictionary
        self.assertIsNotNone(p._dictionary)


class TestVoskRegistration(unittest.TestCase):
    def test_registered(self):
        self.assertIn(Phonemizer.VOSK, PHONEMIZER_REGISTRY)

    def test_get_phonemizer_builds_it(self):
        p = get_phonemizer(Phonemizer.VOSK, Alphabet.VOSK)
        self.assertIsInstance(p, VoskPhonemizer)

    def test_model_threads_through_the_phonemizer_model_knob(self):
        fd, path = tempfile.mkstemp(suffix=".dict")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("дом 1.0 d o1 m\n")
        self.addCleanup(os.remove, path)
        p = get_phonemizer(Phonemizer.VOSK, Alphabet.VOSK, model=path)
        self.assertEqual(p.phonemize_string("дом", "ru"), "d o1 m")

    def test_russian_default_for_vosk_alphabet(self):
        p = phonemizer_for_lang("ru", alphabet=Alphabet.VOSK)
        self.assertIsInstance(p, VoskPhonemizer)
        self.assertIsInstance(phonemizer_for_lang("ru-RU", alphabet=Alphabet.VOSK),
                              VoskPhonemizer)

    def test_vosk_never_selected_for_ipa(self):
        # it emits its own inventory — requesting IPA must fall through
        p = phonemizer_for_lang("ru", alphabet=Alphabet.IPA)
        self.assertNotIsInstance(p, VoskPhonemizer)

    def test_phonemize_lazy_keeps_tokens_whole(self):
        # the lazy path is what consumers stream through: it must yield the same
        # whole phoneme tokens as phonemize(), never a per-character split
        # ("s", "h" would otherwise fold back into "sh" — a different phoneme)
        p = VoskPhonemizer()
        text = "Сходить в кино. Счастье рядом!"
        self.assertEqual(list(p.phonemize_lazy(text, "ru")), p.phonemize(text, "ru"))
        flat = [t for chunk in p.phonemize_lazy(text, "ru") for t in chunk]
        self.assertIn("s", flat)
        self.assertIn("h", flat)
        self.assertTrue(all(len(t) <= 3 for t in flat))
        # every emitted token is a real phoneme/pause, not a bare character of one
        self.assertNotIn("0", flat)
        self.assertNotIn("1", flat)

    def test_module_level_phonemize_facade(self):
        self.assertEqual(phonemize("Привет", "ru", alphabet=Alphabet.VOSK),
                         "p rj i0 vj e0 t")


if __name__ == "__main__":
    unittest.main()
