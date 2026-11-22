"""The tugaphone identity is the base identity, with one warning, where tugaphone gives no revision.

A tugaphone with no ``content_revision`` module, as 1.7.1, and an orthography2ipa whose engine source cannot be read
both phonemize, so their identity must not raise. The expected identity is the base identity of the backend, whose
revision holds the tugaphone version."""
import logging
import sys
import types

import pytest
import tugaphone
from orthography2ipa.exceptions import EngineSourceUnavailable

from scriptconv.phonemizers import pt
from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.pt import TugaphonePhonemizer


@pytest.fixture(autouse=True)
def fresh_cache():
    pt._tugaphone_revision.cache_clear()
    yield
    pt._tugaphone_revision.cache_clear()


def _check(phonemizer, caplog):
    with caplog.at_level(logging.WARNING):
        identity = phonemizer.identity("pt-PT")
        phonemizer.identity("pt-PT")
    assert identity == BasePhonemizer.identity(phonemizer, "pt-PT")
    assert identity.revision.startswith("sc2:")
    assert len([r for r in caplog.records if "no revision" in r.getMessage()]) == 1


def test_a_tugaphone_with_no_content_revision_module(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "tugaphone.content_revision", None)
    _check(TugaphonePhonemizer(), caplog)


def test_an_engine_whose_source_cannot_be_read(monkeypatch, caplog):
    def unreadable(lect):
        raise EngineSourceUnavailable("cannot read the source of orthography2ipa.allophony")

    monkeypatch.setattr(tugaphone, "revision", unreadable)
    _check(TugaphonePhonemizer(), caplog)


def test_an_import_error_inside_the_revision_call_propagates(monkeypatch):
    def broken(lect):
        raise ImportError("cannot import name 'x' from 'tugaphone.registry'")

    monkeypatch.setattr(tugaphone, "revision", broken)
    with pytest.raises(ImportError, match="tugaphone.registry"):
        TugaphonePhonemizer().identity("pt-PT")


def test_an_orthography2ipa_with_no_exceptions_module(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "orthography2ipa.exceptions", None)
    _check(TugaphonePhonemizer(), caplog)


def test_an_orthography2ipa_before_engine_source_unavailable(monkeypatch, caplog):
    # Each orthography2ipa before 7.123.0a1 has an exceptions module with no EngineSourceUnavailable,
    # so the import fails with "cannot import name", not with a missing module.
    monkeypatch.setitem(sys.modules, "orthography2ipa.exceptions", types.ModuleType("orthography2ipa.exceptions"))
    _check(TugaphonePhonemizer(), caplog)
