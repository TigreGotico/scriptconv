"""The pali-tts route: it phonemizes Pali the way the upstream rules do."""
import ast
import pathlib
import sys
import unittest

from scriptconv.phonemizers._vendored import pali_tts as _vendored_module
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.pi import PaliPhonemizer
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY, get_phonemizer

_VENDORED = pathlib.Path(_vendored_module.__file__)

# The upstream self-test of pali_ipa.py at commit a9383004, one row per
# equality it asserts. Expected strings are upstream's own, measured by ear on
# the voices; the to_script rows are left out with to_script itself.
UPSTREAM_CASES = [
    ('jarā', {'stress': False}, 'ɟəɾaː'),
    ('sañjāti', {'stress': False}, 'səɲɟaːtɪ'),
    ('cakkhusamphasso', {'stress': False}, 'cəkkʰʊsəmpʰəssoː'),
    ('dhamma', {'stress': False}, 'dʰəmmə'),
    ('evaṁ me sutaṁ', {'stress': False}, 'eːʋəŋ meː sʊtəŋ'),
    ('saṃgha', {'stress': False}, 'səŋɡʰə'),
    ('saṅgha', {'stress': False}, 'səŋɡʰə'),
    ('mettā', {'stress': False}, 'mettaː'),
    ('sotthi', {'stress': False}, 'sottʰɪ'),
    ('ñāṇa', {'stress': False}, 'ɲaːɳə'),
    ('bhagavato', {}, 'bʰəɡˈʌʋətoː'),
    ('dhamma', {}, 'dʰˈʌmmə'),
    ('nibbānāya', {}, 'nɪbbaːnˈaːjə'),
    ('Katame dve?', {}, 'kˈʌtəmeː dʋˈeː?'),
    ('paṭhamaṁ jhānaṁ', {'stress': False, 'final_m': True}, 'pəʈʰəməm ɟʰaːnəm'),
    ('dhamma', {'full_a': True, 'profile': 'ml'}, 'dʰˈɐmmɐ'),
    ('ñāṇa paññā evaṁ', {'stress': False, 'tune': True}, 'njaːɳə pəɲːjaː eːʋəŋŋ'),
    ('pañca sañjāti', {'stress': False, 'tune': True}, 'pəncə səɲɟaːtɪ'),
    ('Dhammacakka vacī cakkhu', {'full_a': True, 'tune': True}, 'dʰʌmmʌccˈʌkkʌ ʋˈʌcciː cˈʌkkʰʊ'),
    ('pītisukhaṁ', {'full_a': True, 'heavy_back': True}, 'pˈiːtɪsʊkʰʌŋ'),
    ('brahmacariyaṁ', {'full_a': True}, 'bɾʌhmʌcˈʌɾɪjʌŋ'),
    ('passambhayaṁ', {'full_a': True, 'tune': True}, 'pʌssˈʌmbʰʌjjən'),
    ('So evamāha', {'full_a': True, 'tune': True}, 'soːoːoː eːʋʌmˈaːhʌ'),
    ('jarāpi paṭhamaṁ', {'full_a': True, 'tune': True}, 'ɟʌɾˈaːpɪ pˈʌʈʰʌmən'),
    ('sammādiṭṭhi …pe… sammāsamādhi', {'full_a': True, 'tune': True}, 'sʌmmaːdˈɪʈːʰɪ, pejjˈaːlʌ, sʌmmaːsʌmˈaːdʰɪ'),
    ('kiñci muhuttena viharati', {'full_a': True, 'tune': True}, 'kˈɪncɪ muhuttˈeːnʌ ʋɪhˈʌɾatɪ'),
    ('dutiyaṁ imasmiṁ', {'full_a': True, 'tune': True}, 'dˈʊtɪjən ɪmˈʌsmɪm'),
    ('pharitvā', {'full_a': True, 'tune': True}, 'pʰʌɾˈɪtʋaː'),
    ('vimucciṁsūti', {'full_a': True, 'tune': True}, 'ʋɪmʊccɪmsˈuːtɪ'),
    ('arahaṁ ahaṁ', {'full_a': True, 'tune': True}, 'ˈʌɾʌhʌn ˈʌhʌn'),
    ('Ātāpī sampajāno satimā.', {'full_a': True, 'tune': True}, 'aːtˈaːpiː sʌmpʌɟɟˈaːnoːoːoː sˈʌtɪmaː.'),
    ('yogo karaṇīyo.', {'full_a': True, 'tune': True}, 'jˈoːɡoːoːoː kʌɾʌɳˈiːjoː.'),
    ('Diṭṭhupādānaṁ, saṅkhārapaccayā viññāṇaṁ, saṅkhārā.', {'full_a': True, 'tune': True}, 'dɪʈːʰʊpaːdˈaːnən, sʌŋkʰaːɾaːpˈʌccʌjjaː ʋɪɲːjˈaːɳən, sʌŋkʰˈaːɾaː.'),
    ('Kathañca pana, bhikkhave', {'full_a': True, 'tune': True}, 'kʌtʰˈʌncʌ pˈʌna, bʰˈɪkkʰʌʋeː'),
    ('So imameva kāyaṁ aññena byagghehi', {'full_a': True, 'tune': True}, 'soːoːoː ɪmʌmˈeːʋʌ kˈaːjən ʌɲjˈeːnʌ bjjʌɡɡʰˈeːhɪ'),
    ('uposathassa etāni mama vacanāya', {'full_a': True, 'tune': True}, 'ʊpoːsʌtʰˈʌssa eːtˈaːnɪ mˈʌma ʋʌccʌnˈaːjʌ'),
    ('dhārayāmīti pucchāmi', {'full_a': True, 'tune': True}, 'dʰaːɾajaːmˈiːtɪ puːccʰˈaːmɪ'),
    ('bhikkhusammutiyā', {'full_a': True, 'tune': True}, 'bʰɪkkʰʊsˈʌmmʊtɪjjaː'),
    ('Katamā ca, bhikkhave, jarā?', {'full_a': True, 'tune': True}, 'kˈʌtʌmaː cˈʌ, bʰˈɪkkʰʌʋeː, ɟʌɾˈaː?'),
    ('Taṇhā kattha uppajjati', {'full_a': True, 'tune': True}, 'tˈʌɳhaː kˈʌttʰaː ʊppˈʌɟɟatɪ'),
    ('phoṭṭhabba gāminiyā paṭipadāya paṭipadā', {'full_a': True, 'tune': True}, 'phoʈːʰˈʌbbʌ ɡˈaːmɪnɪjjaː pʌʈʈɪpʌdˈaːjʌ pʌʈʈˈɪpʌdaː'),
    ('Tasmātiha, bhikkhave', {'full_a': True, 'tune': True}, 'tʌsmˈaːtɪhaː, bʰˈɪkkʰʌʋeː'),
    ('Tiṇṇaṁ saṅgati', {'full_a': True, 'tune': True}, 'tˈɪɳːən sˈʌŋɡatɪ'),
    ('evaṁ me sutaṁ cakkhuṁ', {'full_a': True, 'tune': True}, 'ˈeːʋən mˈeː sˈʊtən cˈʌkkʰũ'),
]


def _phonemize(text, **options):
    return PaliPhonemizer(**options).phonemize_string(text, "pi")


class TestPaliTTS(unittest.TestCase):
    def test_upstream_self_test(self):
        for text, options, expected in UPSTREAM_CASES:
            with self.subTest(text=text, options=options):
                self.assertEqual(_phonemize(text, **options), expected)

    def test_upstream_self_test_properties(self):
        self.assertEqual(_phonemize("cakkhusamphassapaccayā", full_a=True).count("ʌ"), 6)
        # bhagavato has nothing heavy to move the stress to
        self.assertEqual(_phonemize("bhagavato", heavy_back=True),
                         _phonemize("bhagavato", heavy_back=False))
        # y after a long vowel or inside ññ is not doubled
        self.assertNotIn("jj", _phonemize("kāya paññā", full_a=True, tune=True))
        # the monosyllable hiatus pause does not reach longer words
        self.assertNotIn(", ", _phonemize("āyasmā ānando", full_a=True, tune=True))
        self.assertIn("ʋˈeːdʌjɪtən", _phonemize("vedayitaṁ", full_a=True, tune=True))
        self.assertIn("sʌmphˈʌssʌɟɟən", _phonemize("kāyasamphassajaṁ", full_a=True, tune=True))
        self.assertEqual(_vendored_module.normalize("a ...pa... b"), "a , peyyāla,  b")

    def test_tune_is_off_by_default(self):
        # the pratham respellings double this j; plain rules keep one
        self.assertEqual(_phonemize("passambhayaṁ", full_a=True), "pʌssˈʌmbʰʌjʌŋ")
        self.assertEqual(_phonemize("passambhayaṁ", full_a=True, tune=True), "pʌssˈʌmbʰʌjjən")

    def test_niggahita_spellings_agree(self):
        # ṃ, ṁ and ŋ are three spellings of one letter
        self.assertEqual(_phonemize("evaṃ"), _phonemize("evaṁ"))
        self.assertEqual(_phonemize("evaŋ"), _phonemize("evaṁ"))

    def test_language_is_pali_only(self):
        p = PaliPhonemizer()
        self.assertEqual(p.get_lang("pli"), "pi")
        with self.assertRaises(ValueError):
            p.phonemize_string("dhamma", "hi")

    def test_unknown_profile_is_refused(self):
        with self.assertRaises(ValueError) as caught:
            PaliPhonemizer(profile="ta")
        self.assertIn("'ta'", str(caught.exception))

    def test_registry_entry_resolves(self):
        module, name, extra = PHONEMIZER_REGISTRY[Phonemizer.PALI_TTS]
        self.assertEqual(name, "PaliPhonemizer")
        # no extra: the rules are vendored and need only the standard library
        self.assertIsNone(extra)
        p = get_phonemizer(Phonemizer.PALI_TTS, full_a=True, profile="ml")
        self.assertIsInstance(p, PaliPhonemizer)
        self.assertEqual(p.alphabet, Alphabet.IPA)
        self.assertEqual(p.phonemize_string("dhamma", "pi"), "dʰˈɐmmɐ")

    def test_vendored_rules_import_only_the_standard_library(self):
        roots = set()
        for node in ast.walk(ast.parse(_VENDORED.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                roots.add(node.module.split(".")[0])
        self.assertEqual(roots, {"re", "unicodedata"})
        self.assertLessEqual(roots, sys.stdlib_module_names)

    def test_licence_notice_ships_beside_the_rules(self):
        notice = (_VENDORED.parent / "LICENSE.md").read_text(encoding="utf-8")
        self.assertIn("a93830048ad1c606628331b4922694743dd1fdc8", notice)
        self.assertIn("Copyright (c) 2026 Dhamma.Gift", notice)
        self.assertIn("Permission is hereby granted, free of charge", notice)


if __name__ == "__main__":
    unittest.main()
