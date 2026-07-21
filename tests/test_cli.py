"""Tests for scriptconv.__main__ CLI."""
import pytest
from scriptconv.__main__ import main


def test_no_command_returns_1(capsys):
    assert main([]) == 1
    out = capsys.readouterr().out
    assert "usage" in out.lower()


def test_convert_arpa_ipa(capsys):
    assert main(["convert", "arpa", "ipa", "HH AH0 L OW1"]) == 0
    assert capsys.readouterr().out.strip() == "həloʊ"


def test_convert_xsampa_ipa(capsys):
    assert main(["convert", "x-sampa", "ipa", "S"]) == 0
    assert capsys.readouterr().out.strip() == "ʃ"


def test_convert_invalid_pair(capsys):
    with pytest.raises(SystemExit):
        main(["convert", "buckwalter", "ipa", "x"])


def test_convert_unknown_notation(capsys):
    with pytest.raises(SystemExit):
        main(["convert", "foobar", "ipa", "x"])


def test_detect(capsys):
    assert main(["detect", "Привет мир"]) == 0
    assert capsys.readouterr().out.strip() == "Cyrl"


def test_detect_empty(capsys):
    assert main(["detect", ""]) == 0
    assert capsys.readouterr().out.strip() == "(none)"


def test_distribution(capsys):
    assert main(["distribution", "Hello мир"]) == 0
    out = capsys.readouterr().out.strip()
    assert "Latn" in out
    assert "Cyrl" in out


def test_distribution_empty(capsys):
    assert main(["distribution", "123"]) == 0
    assert capsys.readouterr().out.strip() == "(no script-bearing characters)"


def test_direction_ltr(capsys):
    assert main(["direction", "Hello"]) == 0
    assert capsys.readouterr().out.strip() == "ltr"


def test_direction_rtl(capsys):
    assert main(["direction", "مرحبا"]) == 0
    assert capsys.readouterr().out.strip() == "rtl"


def test_decompose(capsys):
    assert main(["decompose", "한"]) == 0
    out = capsys.readouterr().out.strip()
    assert "ㅎ" in out
    assert "ㅏ" in out
    assert "ㄴ" in out


def test_lang(capsys):
    assert main(["lang", "ru"]) == 0
    assert capsys.readouterr().out.strip() == "Cyrl"


def test_lang_unknown(capsys):
    assert main(["lang", "xyz"]) == 0
    assert capsys.readouterr().out.strip() == "(unknown)"


def test_convert_bad_notation_clean_error(capsys):
    # An invalid notation must produce a clean message, not a raw traceback.
    with pytest.raises(SystemExit) as exc:
        main(["convert", "arpa", "bogus", "AH0"])
    msg = str(exc.value)
    assert msg.startswith("error:")
    assert "valid notations:" in msg


def test_strip_tashkeel(capsys):
    assert main(["strip", "tashkeel", "مُحَمَّد"]) == 0
    assert capsys.readouterr().out.strip() == "محمد"


def test_restyle_pinyin(capsys):
    assert main(["restyle", "pinyin-tone", "mark", "zhong1 guo2"]) == 0
    assert capsys.readouterr().out.strip() == "zhōng guó"


def test_conventions_listing_filtered(capsys):
    assert main(["conventions", "--script", "Arab"]) == 0
    out = capsys.readouterr().out
    assert "tashkeel" in out and "kashida" in out and "niqqud" not in out


def test_strip_unknown_convention_clean_error():
    with pytest.raises(SystemExit) as exc:
        main(["strip", "bogus", "text"])
    assert str(exc.value).startswith("error:")
