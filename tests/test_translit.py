"""Tests for script-level decomposition utilities."""
import pytest

from scriptconv.translit import decompose_hangul


class TestDecomposeHangul:
    @pytest.mark.parametrize("text,expected", [
        ("한", "ㅎㅏㄴ"),
        ("한국어", "ㅎㅏㄴㄱㅜㄱㅇㅓ"),
        ("값", "ㄱㅏㅄ"),          # double coda preserved as written
        ("가", "ㄱㅏ"),            # empty coda
    ])
    def test_decomposition(self, text, expected):
        assert decompose_hangul(text) == expected

    def test_non_hangul_passthrough(self):
        assert decompose_hangul("hello 한 world") == "hello ㅎㅏㄴ world"
        assert decompose_hangul("") == ""
        assert decompose_hangul("123 abc") == "123 abc"

    def test_no_phonology(self):
        """Decomposition is orthographic: the same jamo regardless of
        phonological context (no coda neutralization, no assimilation)."""
        # 국민 pronounced [ɡuŋmin] (ㄱ→ㅇ assimilation) — decomposition
        # must NOT apply it
        assert decompose_hangul("국민") == "ㄱㅜㄱㅁㅣㄴ"

    def test_first_syllable(self):
        """가 (U+AC00) is the first valid Hangul syllable."""
        assert decompose_hangul("가") == "ㄱㅏ"

    def test_last_syllable(self):
        """힣 (U+D7A3) is the last valid Hangul syllable."""
        assert decompose_hangul("힣") == "ㅎㅣㅎ"

    def test_out_of_range_passthrough(self):
        """U+D7A4 is unassigned — should pass through."""
        assert decompose_hangul("\uD7A4") == "\uD7A4"

    def test_jamo_passthrough(self):
        """Precomposed jamo (U+1100–U+11FF) pass through unchanged."""
        assert decompose_hangul("ㅎㅏㄴ") == "ㅎㅏㄴ"

    def test_compatibility_jamo_passthrough(self):
        """Compatibility jamo (U+3130–U+318F) pass through unchanged."""
        assert decompose_hangul("ㄱㅎ") == "ㄱㅎ"


class TestDecomposeHangulForms:
    def test_conjoining_recombines_via_nfc(self):
        import unicodedata
        conj = decompose_hangul("국민", form="conjoining")
        # Conjoining jamo recombine into the original syllables under NFC.
        assert unicodedata.normalize("NFC", conj) == "국민"
        assert conj != "국민"  # decomposed, not a no-op

    def test_drop_silent_initial_compatibility(self):
        # ㅇ (ieung) placeholder onset is dropped, coda ㅇ is kept.
        assert decompose_hangul("안", drop_silent_initial=True) == "ㅏㄴ"
        assert decompose_hangul("강", drop_silent_initial=True) == "ㄱㅏㅇ"

    def test_drop_silent_initial_conjoining(self):
        import unicodedata
        out = decompose_hangul("안", form="conjoining", drop_silent_initial=True)
        assert "ᄋ" not in out  # no conjoining ieung
        # vowel + final n present
        assert unicodedata.normalize("NFC", "ᄋ" + out) == "안"

    def test_invalid_form_raises(self):
        with pytest.raises(ValueError):
            decompose_hangul("가", form="bogus")


class TestKanaTransliteration:
    def test_hira_to_kana(self):
        from scriptconv.translit import hira_to_kana
        assert hira_to_kana("ひらがな") == "ヒラガナ"
        assert hira_to_kana("こんにちは") == "コンニチハ"

    def test_kana_to_hira(self):
        from scriptconv.translit import kana_to_hira
        assert kana_to_hira("カタカナ") == "かたかな"

    def test_round_trip(self):
        from scriptconv.translit import hira_to_kana, kana_to_hira
        for s in ["こんにちは", "ありがとう", "さようなら"]:
            assert kana_to_hira(hira_to_kana(s)) == s

    def test_long_vowel_mark_passthrough(self):
        from scriptconv.translit import kana_to_hira
        # ー (U+30FC) has no hiragana form, stays as-is.
        assert kana_to_hira("ラーメン") == "らーめん"

    def test_non_kana_passthrough(self):
        from scriptconv.translit import hira_to_kana, kana_to_hira
        assert hira_to_kana("abc 123") == "abc 123"
        assert kana_to_hira("") == ""
