"""gruut's sentence rules must not change its cached lexicon pronunciations,
and the first language of a thread must not decide how later calls read.

The French liaison and the Catalan fusion rules of gruut change the phoneme
list of a word in place. gruut gives each word the list it caches for the
lexicon entry, so without a copy one liaison changes every later reading of
the same word in the process.

A gruut processor reads every sentence after the first of a call, and the
part-of-speech tags of the call, with the language it was made for.

The expected values come from gruut's own lexicon databases and the rules in
``gruut/lang.py``, not from a run of the phonemizer.
"""

import sqlite3
import threading
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import gruut.text_processor
import gruut_lang_ca
import gruut_lang_en
import gruut_lang_fr

from scriptconv.phonemizers.mul import GruutPhonemizer


def lexicon(lang_module, word: str, role: str = "") -> str:
    """The pronunciation gruut reads for a word and role: the first row by pron_order."""
    db = Path(lang_module.get_lang_dir()) / "lexicon.db"
    with closing(sqlite3.connect(str(db))) as conn:
        row = conn.execute(
            "SELECT phonemes FROM word_phonemes WHERE word = ? AND role = ? ORDER BY pron_order",
            (word, role),
        ).fetchone()
    return row[0].replace(" ", "")


def in_new_thread(calls, barrier=None):
    """Phonemize (text, lang) pairs in a new thread, which starts with no gruut state."""
    outputs = []

    def run():
        phonemizer = GruutPhonemizer()
        for i, (text, lang) in enumerate(calls):
            outputs.append(phonemizer.phonemize_string(text, lang))
            if barrier is not None and i == 0:
                barrier.wait(timeout=60)

    thread = threading.Thread(target=run)
    thread.start()
    return thread, outputs


def run_in_new_thread(calls):
    thread, outputs = in_new_thread(calls)
    thread.join()
    return outputs


class TestFrenchLiaison(unittest.TestCase):
    """fr_post_process_sentence: a pronoun that ends in a silent "s" takes a
    "z" before a verb that starts with a vowel. A consonant start takes none."""

    def assert_no_leak(self, pronoun: str, consonant_verb: str, vowel_verb: str):
        phonemizer = GruutPhonemizer()
        pron = lexicon(gruut_lang_fr, pronoun)
        plain = f"{pron} {lexicon(gruut_lang_fr, consonant_verb)}"
        liaison = f"{pron}z {lexicon(gruut_lang_fr, vowel_verb)}"

        self.assertEqual(phonemizer.phonemize_string(f"{pronoun} {consonant_verb}", "fr"), plain)
        self.assertEqual(phonemizer.phonemize_string(f"{pronoun} {vowel_verb}", "fr"), liaison)
        self.assertEqual(phonemizer.phonemize_string(f"{pronoun} {consonant_verb}", "fr"), plain)
        self.assertEqual(phonemizer.phonemize_string(f"{pronoun} {vowel_verb}", "fr"), liaison)

    def test_nous(self):
        self.assert_no_leak("nous", "dînons", "allons")

    def test_vous(self):
        self.assert_no_leak("vous", "dînez", "allez")


class TestCatalanFusion(unittest.TestCase):
    """fusion_if_needed, case 3: a final neutral vowel drops before a word
    that starts with a neutral vowel. The word alone keeps it."""

    def test_aimara(self):
        phonemizer = GruutPhonemizer()
        word = lexicon(gruut_lang_ca, "aimara")
        self.assertTrue(word.endswith("ə"))
        fused = f"{word[:-1]} {lexicon(gruut_lang_ca, 'ablació')}"

        self.assertEqual(phonemizer.phonemize_string("aimara", "ca"), word)
        self.assertEqual(phonemizer.phonemize_string("aimara ablació", "ca"), fused)
        self.assertEqual(phonemizer.phonemize_string("aimara", "ca"), word)
        self.assertEqual(phonemizer.phonemize_string("aimara ablació", "ca"), fused)


FR_TEXT = "Les enfants. Les chats. Les enfants."
EN_TEXT = "Hello. I will record a song. The record is long."


def fr_expected() -> str:
    """fr_post_process_sentence: a determiner that ends in a silent "s" takes a
    "z" before a noun that starts with a vowel, in every sentence."""
    les = lexicon(gruut_lang_fr, "les")
    enfants = lexicon(gruut_lang_fr, "enfants")
    chats = lexicon(gruut_lang_fr, "chats")
    return f"{les}z {enfants} . {les} {chats} . {les}z {enfants} ."


def en_record_readings(output: str):
    """The two readings of "record" in EN_TEXT: after "will" and after "the"."""
    words = output.split()
    return words[4], words[9]


EN_RECORD = (lexicon(gruut_lang_en, "record", "gruut:VB"), lexicon(gruut_lang_en, "record", "gruut:NN"))


class TestFirstLanguageOfThread(unittest.TestCase):
    """Each call reads all its sentences, and tags them, in its own language,
    whatever language the thread read first. gruut picks the lexicon row whose
    role matches the part-of-speech tag: the verb after "will", the noun after
    "the"."""

    def test_french_after_english(self):
        outputs = run_in_new_thread([("Hello.", "en"), (FR_TEXT, "fr")])
        self.assertEqual(outputs[1], fr_expected())

    def test_english_after_french(self):
        outputs = run_in_new_thread([("Bonjour.", "fr"), (EN_TEXT, "en")])
        self.assertEqual(en_record_readings(outputs[1]), EN_RECORD)

    def test_two_threads_two_languages(self):
        barrier = threading.Barrier(2)
        thread_en, outputs_en = in_new_thread([("Hello.", "en"), (FR_TEXT, "fr"), (EN_TEXT, "en")], barrier)
        thread_fr, outputs_fr = in_new_thread([("Bonjour.", "fr"), (EN_TEXT, "en"), (FR_TEXT, "fr")], barrier)
        thread_en.join()
        thread_fr.join()
        self.assertEqual(outputs_en[1], fr_expected())
        self.assertEqual(en_record_readings(outputs_en[2]), EN_RECORD)
        self.assertEqual(en_record_readings(outputs_fr[1]), EN_RECORD)
        self.assertEqual(outputs_fr[2], fr_expected())



class TestFailedFirstLoad(unittest.TestCase):
    """A processor is cached only with the copying lookup. One failed settings
    load must not leave a processor behind that leaks the liaison."""

    def test_liaison_does_not_leak_after_a_failed_load(self):
        real_get_settings = gruut.text_processor.get_settings
        loads = []

        def fail_once(*args, **kwargs):
            loads.append(args)
            if len(loads) == 1:
                raise OSError("injected")
            return real_get_settings(*args, **kwargs)

        outputs = []

        def run():
            phonemizer = GruutPhonemizer()
            for text in ["nous dînons", "nous dînons", "nous allons", "nous dînons"]:
                try:
                    outputs.append(phonemizer.phonemize_string(text, "fr"))
                except OSError as e:
                    outputs.append(str(e))

        with mock.patch("gruut.text_processor.get_settings", fail_once):
            thread = threading.Thread(target=run)
            thread.start()
            thread.join()

        nous = lexicon(gruut_lang_fr, "nous")
        plain = f"{nous} {lexicon(gruut_lang_fr, 'dînons')}"
        liaison = f"{nous}z {lexicon(gruut_lang_fr, 'allons')}"
        self.assertEqual(outputs, ["injected", plain, liaison, plain])


if __name__ == "__main__":
    unittest.main()
