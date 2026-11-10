"""Epitran reads Korean in Hangul only.

The bare tag ``ko`` defaults to the Kore script, Hangul plus Hanja. The
epitran ``kor-Hang`` map passes Hanja through unread, so a Korean request
must name the Hang script, and the refusal tells the caller how to do so.
"""
import unittest

from scriptconv.phonemizers.mul import EpitranPhonemizer


class TestEpitranKoreanScript(unittest.TestCase):
    def test_korean_without_hangul_script_raises_with_hint(self):
        for tag in ["ko", "ko-KR", "ko-KO", "kor", "ko-Kore", "kor-KR", "kor-Kore"]:
            with self.subTest(tag=tag):
                with self.assertRaises(ValueError) as ctx:
                    EpitranPhonemizer.get_lang(tag)
                self.assertIn("ko-Hang", str(ctx.exception))
                self.assertIn(tag, str(ctx.exception))

    def test_hangul_script_request_resolves(self):
        for tag in ["ko-Hang", "kor-Hang"]:
            with self.subTest(tag=tag):
                self.assertEqual(EpitranPhonemizer.get_lang(tag), "kor-Hang")


if __name__ == "__main__":
    unittest.main()
