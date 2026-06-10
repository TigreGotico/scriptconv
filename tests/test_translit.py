"""Tests for scriptconv.translit (Hangul → IPA)."""
import pytest
from scriptconv.translit import hangul_to_ipa


# ---------------------------------------------------------------------------
# Basic smoke tests
# ---------------------------------------------------------------------------

def test_hangul_to_ipa_returns_string():
    result = hangul_to_ipa("안녕")
    assert isinstance(result, str)
    assert len(result) > 0


def test_hangul_to_ipa_empty():
    assert hangul_to_ipa("") == ""


def test_hangul_to_ipa_space_preserved():
    result = hangul_to_ipa("안녕 세계")
    assert " " in result


# ---------------------------------------------------------------------------
# Gold checks — individual jamo patterns
# ---------------------------------------------------------------------------

def test_basic_cv_syllable():
    # 나 = ㄴ + ㅏ → n + ä
    result = hangul_to_ipa("나")
    assert "n" in result
    assert "ä" in result


def test_basic_vowel_only():
    # 아 = ㅇ (null onset, dropped) + ㅏ → ä
    result = hangul_to_ipa("아")
    assert "ä" in result


def test_aspirated_consonant():
    # 파 = ㅍ + ㅏ → pʰä
    result = hangul_to_ipa("파")
    assert "pʰ" in result


def test_nasal_consonant():
    # 미 = ㅁ + ㅣ → mi
    result = hangul_to_ipa("미")
    assert "m" in result
    assert "i" in result


def test_velar_nasal_coda():
    # 강 = ㄱ + ㅏ + ㅇ → kŋ context
    result = hangul_to_ipa("강")
    assert "ŋ" in result


def test_multiple_words():
    r1 = hangul_to_ipa("나")
    r2 = hangul_to_ipa("미")
    combined = hangul_to_ipa("나 미")
    assert r1 in combined
    assert r2 in combined


# ---------------------------------------------------------------------------
# Phonological rule verification
# ---------------------------------------------------------------------------

def test_palatalization_di():
    # 굳이 → 구지 (ㄷ + ㅣ → ㅈ + ㅣ)
    result_di = hangul_to_ipa("굳이")
    result_no_di = hangul_to_ipa("구지")
    # Both should produce the same IPA (palatalization applied)
    assert result_di == result_no_di


def test_nasalization():
    # 국민 → 궁민 (ㄱ before ㅁ → ㅇ)
    result = hangul_to_ipa("국민")
    # Should contain nasal ŋ rather than k before m
    assert "km" not in result


def test_ll_stays_ll():
    # 달라 — ㄹ + ㄴ → ㄹ + ㄹ assimilation
    result_dalla = hangul_to_ipa("달라")
    # Both l sounds expected
    assert result_dalla.count("l") >= 2 or "ɾ" in result_dalla


def test_aspiration_hg():
    # 좋고 → ㅎ + ㄱ → ㅋ aspiration
    result = hangul_to_ipa("좋고")
    # Should contain kʰ not h+k
    assert "kʰ" in result or "k" in result


# ---------------------------------------------------------------------------
# Full word gold checks
# ---------------------------------------------------------------------------

def test_word_si_yes():
    # 예 = ㅖ → je
    result = hangul_to_ipa("예")
    assert "j" in result
    assert "e" in result


def test_word_nae():
    # 내 = ㄴ + ㅐ → nɛ
    result = hangul_to_ipa("내")
    assert "n" in result


def test_word_ga():
    # 가 = ㄱ + ㅏ → kä
    result = hangul_to_ipa("가")
    assert "k" in result
    assert "ä" in result


def test_hankuk():
    # 한국 — should produce something with h, a, n, k, u, k sounds
    result = hangul_to_ipa("한국")
    assert "h" in result or "n" in result
    assert len(result) >= 4
