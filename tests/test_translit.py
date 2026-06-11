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
