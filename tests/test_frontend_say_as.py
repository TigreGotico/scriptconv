"""TextFrontend.say_as: one run of text in the form that an SSML say-as element names, through the normaliser hook."""
import logging
from functools import partial

import pytest

from scriptconv.frontend import FrontendConfig, TextFrontend, spoken_normalizer
from scriptconv.phonemizers.base import GraphemePhonemizer, StageError
from scriptconv.phonemizers.enums import Alphabet
from text2spoken import NormalizationParams, SayAs, normalize


class Owner(GraphemePhonemizer):
    """A backend that runs its own normalisation."""
    owned_stages = frozenset({"normalize"})


def frontend(lang="en-US", strict=False, backend=None, **config):
    return TextFrontend(FrontendConfig(lang, strict=strict, **config), backend or GraphemePhonemizer(Alphabet.IPA))


@pytest.mark.parametrize("text,interpret_as,format,expected", [
    ("123", "ordinal", None, "one hundred twenty-third"),
    ("01/02/1960", "date", "dmy", "February first nineteen sixty"),
    ("3981900", "telephone", None, "three nine eight one nine zero zero"),
])
def test_the_say_as_reads_through_the_hook_of_spoken_normalizer(text, interpret_as, format, expected):
    """The expected values are the rows SA01, SA06 and SA13 of text2spoken tests/data/say_as/rows.tsv."""
    assert frontend(normalizer=spoken_normalizer()).say_as(text, interpret_as, format) == expected


def test_the_say_as_reads_with_the_params_that_the_hook_binds():
    params = NormalizationParams(clock="24h")
    hook = partial(spoken_normalizer(), params=params)
    expected = normalize("00:01", "en-US", params, say_as=SayAs(interpret_as="time"))
    assert expected != normalize("00:01", "en-US", say_as=SayAs(interpret_as="time"))
    assert frontend(normalizer=hook).say_as("00:01", "time") == expected


def test_the_lang_of_the_call_wins():
    assert frontend("en-US", normalizer=spoken_normalizer()).say_as("3", "ordinal", lang="pt-PT") == "terceiro"


def test_the_hook_runs_when_the_backend_owns_normalisation():
    assert frontend(normalizer=spoken_normalizer(), backend=Owner(Alphabet.IPA)).say_as("123", "ordinal") \
        == "one hundred twenty-third"


@pytest.mark.parametrize("strict", [False, True])
def test_with_no_hook_the_text_reads_as_written_with_one_warning(caplog, strict):
    with caplog.at_level(logging.WARNING, logger="scriptconv.frontend"):
        assert frontend(strict=strict).say_as("123", "ordinal") == "123"
    records = [r for r in caplog.records if r.name == "scriptconv.frontend"]
    assert len(records) == 1 and records[0].levelno == logging.WARNING
    assert "`normalize` extra" in records[0].getMessage()


@pytest.mark.parametrize("strict", [False, True])
def test_without_text2spoken_the_text_reads_as_written_with_one_warning(caplog, monkeypatch, strict):
    import sys

    monkeypatch.setitem(sys.modules, "text2spoken", None)
    with caplog.at_level(logging.WARNING, logger="scriptconv.frontend"):
        assert frontend(strict=strict, normalizer=lambda text, lang, **_: "spoken").say_as("123", "ordinal") == "123"
    assert ["`normalize` extra" in r.getMessage() for r in caplog.records if r.name == "scriptconv.frontend"] \
        == [True]


def test_a_hook_with_no_say_as_keyword_keeps_the_text_or_raises_in_strict_mode(caplog):
    def hook(text, lang):
        return text.upper()

    with caplog.at_level(logging.WARNING, logger="scriptconv.frontend"):
        assert frontend(normalizer=hook).say_as("abc", "characters") == "abc"
    assert any("normalize failed" in r.getMessage() for r in caplog.records)
    with pytest.raises(StageError):
        frontend(strict=True, normalizer=hook).say_as("abc", "characters")
