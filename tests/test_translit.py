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
