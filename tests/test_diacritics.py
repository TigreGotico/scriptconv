"""Pure-python tests for scriptconv.diacritics strip/overlay helpers.

No optional backend is required — strip_diacritics/_overlay_marks/_supports_strip
never load a phonemizer model.
"""
import os

import pytest

from scriptconv.diacritics import (
    strip_diacritics,
    _overlay_marks,
    _supports_strip,
    _STRESS_MARKS,
    _ARABIC_MARKS,
    _HEBREW_MARKS,
    STRESS_LANGS,
)


def test_strip_removes_combining_acute_preserves_cyrillic():
    assert strip_diacritics("мой родно́й край", "ru") == "мой родной край"


def test_strip_preserves_precomposed_cyrillic_letters():
    # й (U+0439) and ё (U+0451) are precomposed, not combining marks — they
    # must survive stripping even alongside a combining acute.
    text = "ёж, война́, май"  # combining acute (U+0301) after "а" in "война́"
    stripped = strip_diacritics(text, "ru")
    assert "ё" in stripped
    assert "й" in stripped
    assert stripped == "ёж, война, май"


def test_strip_arabic_removes_tashkeel_preserves_consonants():
    assert strip_diacritics("مُحَمَّد", "ar") == "محمد"


def test_strip_arabic_preserves_hamza_carrier():
    stripped = strip_diacritics("أَحْمَد", "ar")
    assert stripped.startswith("أ")


def test_strip_hebrew_removes_niqqud_preserves_consonants():
    # שָׁלוֹם with niqqud -> bare consonants שלום
    stripped = strip_diacritics("שָׁלוֹם", "he")
    assert stripped == "שלום"


@pytest.mark.parametrize("text,lang", [
    ("café", "pt"),
    ("café", "en"),
    ("café", "es"),
    ("café", "arg"),
    ("café", "her"),
    ("café", "arn"),
])
def test_strip_raises_for_native_orthography_langs(text, lang):
    with pytest.raises(ValueError):
        strip_diacritics(text, lang)


@pytest.mark.parametrize("lang", [
    "ru", "uk", "be", "ar", "ar-SA", "he", "he-IL", "bg", "ka",
])
def test_supports_strip_true(lang):
    assert _supports_strip(lang) is True


@pytest.mark.parametrize("lang", [
    "pt", "pt-PT", "en", "arg", "her", "arn",
])
def test_supports_strip_false(lang):
    assert _supports_strip(lang) is False


def test_overlay_marks_stress_lang():
    lang = next(iter(STRESS_LANGS))
    assert _overlay_marks(lang) == _STRESS_MARKS


def test_overlay_marks_arabic():
    assert _overlay_marks("ar") == _ARABIC_MARKS


def test_overlay_marks_hebrew():
    assert _overlay_marks("he") == _HEBREW_MARKS


def test_overlay_marks_none_for_native_orthography():
    assert _overlay_marks("pt") is None
    assert _overlay_marks("en") is None


class TestHebrewDiacritizerAutoProvisions:
    def test_no_model_given_auto_provisions(self, monkeypatch):
        from scriptconv import diacritics

        monkeypatch.setitem(diacritics._PHONIKUD_CACHE, "/sentinel/path.onnx", object())
        monkeypatch.setattr(diacritics, "_default_phonikud_model",
                             lambda: "/sentinel/path.onnx")
        result = diacritics._phonikud(None)
        assert result is diacritics._PHONIKUD_CACHE["/sentinel/path.onnx"]

    def test_explicit_path_bypasses_provisioner(self, monkeypatch):
        from scriptconv import diacritics

        calls = []
        monkeypatch.setattr(diacritics, "_default_phonikud_model",
                             lambda: calls.append(1) or "/should/not/be/used.onnx")

        class FakePhonikud:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(diacritics, "_PHONIKUD_CACHE", {})
        import sys
        import types
        fake_mod = types.ModuleType("phonikud_onnx")
        fake_mod.Phonikud = FakePhonikud
        monkeypatch.setitem(sys.modules, "phonikud_onnx", fake_mod)

        result = diacritics._phonikud("/explicit/path.onnx")
        assert result.model == "/explicit/path.onnx"
        assert calls == []  # provisioner never invoked


class TestPhonikudModelResolver:
    def test_callable_resolver_invoked_lazily(self, monkeypatch):
        from scriptconv import diacritics

        calls = []

        def resolver():
            calls.append(1)
            return "/from/callable.onnx"

        class FakePhonikud:
            def __init__(self, model):
                self.model = model

        monkeypatch.setattr(diacritics, "_PHONIKUD_CACHE", {})
        import sys
        import types
        fake_mod = types.ModuleType("phonikud_onnx")
        fake_mod.Phonikud = FakePhonikud
        monkeypatch.setitem(sys.modules, "phonikud_onnx", fake_mod)

        assert calls == []  # not resolved at construction
        result = diacritics._phonikud(resolver)
        assert calls == [1]
        assert result.model == "/from/callable.onnx"


class TestDefaultPhonikudModelProvisioning:
    def test_downloads_to_cache_dir_and_returns_path(self, monkeypatch, tmp_path):
        from scriptconv import diacritics

        monkeypatch.setenv("SCRIPTCONV_CACHE", str(tmp_path))
        calls = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

            def read(self, n):
                if calls and calls[-1] == "read-done":
                    return b""
                calls.append("read-done")
                return b"dummy-onnx-bytes"

        def fake_urlopen(url):
            calls.append(("urlopen", url))
            return FakeResponse()

        monkeypatch.setattr(diacritics.urllib.request, "urlopen", fake_urlopen)

        path = diacritics._default_phonikud_model()
        assert path == str(tmp_path / "scriptconv" / "phonikud" / "phonikud-1.0.int8.onnx")
        assert os.path.isfile(path)

        # idempotent: second call must not re-download
        urlopen_calls_before = sum(1 for c in calls if isinstance(c, tuple))
        diacritics._default_phonikud_model()
        urlopen_calls_after = sum(1 for c in calls if isinstance(c, tuple))
        assert urlopen_calls_before == urlopen_calls_after == 1

    def test_failed_download_leaves_no_partial_file(self, monkeypatch, tmp_path):
        from scriptconv import diacritics

        monkeypatch.setenv("SCRIPTCONV_CACHE", str(tmp_path))

        def failing_urlopen(url):
            raise OSError("network unavailable")

        monkeypatch.setattr(diacritics.urllib.request, "urlopen", failing_urlopen)

        with pytest.raises(OSError):
            diacritics._default_phonikud_model()

        dest = tmp_path / "scriptconv" / "phonikud" / "phonikud-1.0.int8.onnx"
        assert not dest.exists()
        cache_dir = tmp_path / "scriptconv" / "phonikud"
        if cache_dir.exists():
            assert list(cache_dir.iterdir()) == []


class TestEuropeanPortugueseSenseDiacritics:
    """Real bifonia — it is on PyPI, so this exercises the actual backend."""

    def test_thirst_sense_gets_closed_vowel(self):
        from scriptconv.diacritics import diacritize
        out = diacritize("Tenho muita sede hoje.", "pt")
        assert out == "Tenho muita sêde hoje."

    def test_seat_sense_gets_open_vowel(self):
        from scriptconv.diacritics import diacritize
        out = diacritize("A sede da empresa fica em Lisboa.", "pt")
        assert out == "A séde da empresa fica em Lisboa."

    def test_no_homograph_unchanged(self):
        from scriptconv.diacritics import diacritize
        text = "O cão correu no jardim."
        assert diacritize(text, "pt") == text

    def test_brazilian_portuguese_excluded(self):
        from scriptconv.diacritics import diacritize
        text = "Tenho muita sede hoje."
        assert diacritize(text, "pt-BR") == text


class TestEastSlavicStressRouting:
    """stressonnx is not yet on PyPI — routing is verified against a stub."""

    def _stub(self, calls):
        import types
        mod = types.ModuleType("stressonnx")

        def stress(text, lang, model=None):
            calls.append((text, lang, model))
            return "STRESSED"

        mod.stress = stress
        return mod

    def test_russian_routes_to_stress_backend(self):
        import sys
        from unittest import mock
        from scriptconv.diacritics import diacritize
        calls = []
        with mock.patch.dict(sys.modules, {"stressonnx": self._stub(calls)}):
            out = diacritize("замок стоит", "ru", model="silero")
        assert out == "STRESSED"
        assert calls == [("замок стоит", "ru", "silero")]

    def test_ukrainian_and_belarusian_route_too(self):
        import sys
        from unittest import mock
        from scriptconv.diacritics import diacritize
        for lang in ("uk", "be"):
            calls = []
            with mock.patch.dict(sys.modules, {"stressonnx": self._stub(calls)}):
                diacritize("текст", lang, model="ruaccent")
            assert calls == [("текст", lang, "ruaccent")], lang

    def test_additional_stressonnx_languages_route_too(self):
        import sys
        from unittest import mock
        from scriptconv.diacritics import diacritize
        for lang in ("kk", "hy", "az-Latn"):
            calls = []
            with mock.patch.dict(sys.modules, {"stressonnx": self._stub(calls)}):
                diacritize("text", lang, model="simple")
            assert calls == [("text", lang, "simple")], lang

    def test_berber_does_not_false_match_belarusian(self):
        import sys
        from unittest import mock
        from scriptconv.diacritics import diacritize
        calls = []
        with mock.patch.dict(sys.modules, {"stressonnx": self._stub(calls)}):
            out = diacritize("azul", "ber")
        assert out == "azul"
        assert calls == []

    def test_missing_stressonnx_raises_named_importerror(self):
        import sys
        from unittest import mock
        from scriptconv.diacritics import diacritize
        with mock.patch.dict(sys.modules, {"stressonnx": None}):
            with pytest.raises(ImportError) as ctx:
                diacritize("замок", "ru")
        assert "stressonnx" in str(ctx.value)
