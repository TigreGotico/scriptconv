"""Diacritization: language routing, cached backends, and the graph edges.

Diacritization (Arabic tashkeel, Hebrew niqqud, East-Slavic/Turkic/Caucasian
word stress, European-Portuguese homograph sense marks) maps the ``"text"``
node to a lang-contextual ``"text-diacritized"`` node. Phonemizers run no
diacritizer; a backend only removes, through :func:`replace_stress_mark`, a
stress mark that it does not read. Like :func:`scriptconv.phonemizers.register`
the edges are opt-in, so ``DEFAULT_GRAPH`` stays free of them::

    from scriptconv.graph import DEFAULT_GRAPH
    from scriptconv import diacritics, phonemizers
    g = DEFAULT_GRAPH.extend(diacritics.register).extend(phonemizers.register)

    g.convert("замок стоит на горе", "text", "text-diacritized", lang="ru")
    # 'за́мок сто́ит на горе́'    — just the diacritized text

    g.convert("Tenho muita sede hoje.", "text", "text-diacritized", lang="pt")
    # 'Tenho muita sêde hoje.'

The diacritization edge is model-based (``lossless=False``), so ``"text" ->
"ipa"`` keeps the direct phonemization edge; the diacritized route is taken
only when a caller asks for ``"text-diacritized"``.

The strip edge (``"text-diacritized" -> "text"``) exists only for overlay
diacritics: Arabic/Hebrew vocalization (text2tashkeel, phonikud) and stress
(stressonnx). It removes only the codepoints each backend adds, never every
combining mark, so precomposed native letters survive (Cyrillic й/ё, Latvian
macrons, Azerbaijani ç/ö, Arabic hamza carriers أ إ آ ؤ ئ). Diacritics that
are native orthography (European Portuguese, via bifonia) refuse the strip
with :class:`ValueError`, as ``café`` must never become ``cafe``. Arabic is
decided by linguatag and the other families by exact primary subtag, so
Aragonese (``arg``), Herero (``her``) and Mapudungun (``arn``) are never read
as Arabic or Hebrew.

A stress mark and a letter-forming mark can be the same codepoint. In NFD text
the Macedonian letters ѓ and ќ are г and к followed by U+0301, the codepoint
stressonnx uses for stress. Strip keeps an acute or grave when it composes (NFC)
with the letter before it into a letter of the language's alphabet, and removes
it otherwise. A kept mark is written composed with its letter. So when U+0301
comes right after г or к, as in NFD ѓ and ќ, strip writes the precomposed
letter that NFC input gives. Unicode has eight Cyrillic letters whose NFD form
ends in U+0300 or U+0301 (ѐ ѓ ќ ѝ and their capitals), and no Armenian or
Georgian letter of that kind:

- Macedonian: the 31-letter alphabet includes ѓ and ќ (Институт за македонски
  јазик „Крсте Мисирков“, Правопис на македонскиот јазик, 2nd ed., Skopje
  2017, §1, p. 3). Strip keeps these letters.
- Macedonian ѐ and ѝ are е and и with a supralinear sign, and the Pravopis
  lists that sign, not these letters (§325, p. 141): „Надреден знак (`) се
  става над е во кратката заменска форма нѐ, над и во кратката заменска форма
  ѝ и во количествената заменска форма сѐ“. In Bulgarian the grave over и
  and е is the usual stress mark (Институт за български език при БАН, Езикови
  справки, „Ударение“: промѝл, процѐнт, тѐстова), and the same sign writes the
  pronoun ѝ. Strip removes a combining grave in both languages, as it does
  any other stress mark.
- Latvian writes no letter with an acute or grave (Kalnača & Lokmane, Latvian
  Grammar, University of Latvia Press 2021, p. 20). A Latin vowel with a
  stress acute composes to a precomposed form such as á, but á is not a
  Latvian letter, so strip removes the acute.
"""
import functools
import hashlib
import http.client
import logging
import os
import re
import tempfile
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from scriptconv.graph import Edge
from scriptconv.phonemizers.base import (
    STRESS_MARK, BasePhonemizer, ModelUnavailableError, _primary_subtag,
)

LOG = logging.getLogger(__name__)

#: The lang-contextual node produced by diacritization; it exists only in opted-in graphs.
DIACRITIZED = "text-diacritized"

# Languages with free word stress that ordinary spelling leaves unwritten. In
# East Slavic unstressed vowels also reduce (Russian unstressed "о" is [ɐ] or
# [ə]), so a missing mark changes vowel quality. stressonnx writes a combining
# acute (U+0301) after the stressed vowel for 26 BCP-47 tags over these 24 primary
# subtags; az and uz each have a Cyrillic and a Latin variant.
STRESS_LANGS = {
    "az", "ba", "be", "bg", "cv", "hy", "ka", "kbd", "kjh", "kk", "ky", "lv",
    "mdf", "mk", "myv", "ru", "sah", "sl", "tg", "tt", "udm", "uk", "uz", "xal",
}


def _is_european_portuguese(lang: str) -> bool:
    """True for a tag at linguatag distance 0 from ``pt-PT``: ``pt``, ``por`` and the European lects, not ``pt-BR``.

    Only a ``pt`` or ``por`` primary subtag loads linguatag, so other callers
    do not need the ``phonemizers`` extra.
    """
    if _primary_subtag(lang) not in ("pt", "por"):
        return False
    try:
        from linguatag import lang_distance
    except ImportError as e:
        raise ImportError(
            "diacritization language routing requires the linguatag package: "
            "pip install scriptconv[phonemizers]") from e
    return lang_distance(lang, "pt-PT") == 0


# linguatag measures ``ar`` with any region, Hassaniyya (``mey``) and each
# individual Arabic language (``arz``, ``apc``, ...) in Arabic script at 5 or
# less from ``ar``. The same language in another script is further away.
_ARABIC_SCRIPT_DISTANCE = 5


def _is_arabic_script_arabic(lang: str) -> bool:
    """True for a tag that names Arabic, or a variety of Arabic, in Arabic script.

    ``is_arabic_variety`` names the language (``ar``, the ISO 639-3 ``ara``
    macrolanguage, Hassaniyya ``mey``); ``lang_distance`` to ``ar`` adds the
    script, because tashkeel marks only Arabic script. So ``ar-Latn``, and
    ``acy`` and ``pga``, which CLDR writes in Latin script, return False, as do
    Persian and Urdu.

    ISO 639-1 gives Arabic one two-letter code, ``ar``, so any other two-letter
    subtag returns False before linguatag loads.
    """
    p = _primary_subtag(lang)
    if len(p) == 2 and p != "ar":
        return False
    try:
        from linguatag import is_arabic_variety, lang_distance
    except ImportError as e:
        raise ImportError(
            "diacritization language routing requires the linguatag package: "
            "pip install scriptconv[phonemizers]") from e
    return (is_arabic_variety(lang)
            and lang_distance(lang, "ar") <= _ARABIC_SCRIPT_DISTANCE)


#: Primary subtags that stressonnx serves only with a script subtag (az-Cyrl, uz-Latn, ...).
_SCRIPT_AMBIGUOUS_STRESS_LANGS = frozenset({"az", "uz"})


def _is_stress_lang_fallback(lang: str) -> bool:
    """:func:`_is_stress_lang` without stressonnx installed, by the same resolution rules.

    az and uz need a Cyrl or Latn script subtag; every other member takes no
    script subtag.
    """
    normalized = lang.replace("_", "-")
    parts = normalized.split("-")
    p = parts[0].lower()
    if p not in STRESS_LANGS:
        return False
    has_script = len(parts) >= 2 and len(parts[1]) == 4 and parts[1].isalpha()
    if p in _SCRIPT_AMBIGUOUS_STRESS_LANGS:
        return has_script and parts[1].title() in ("Cyrl", "Latn")
    return not has_script


def _is_stress_lang(lang: str) -> bool:
    """True if stressonnx's own ``resolve_lang`` resolves *lang* to a model.

    A bare ``az`` or ``uz`` does not resolve; ``ru-RU`` does. Without the
    ``stress`` extra, :func:`_is_stress_lang_fallback` gives the same answer.
    """
    try:
        from stressonnx import ALL_LANGS
        from stressonnx.langs import resolve_lang
        from stressonnx.errors import UnsupportedLanguageError
    except ImportError:
        return _is_stress_lang_fallback(lang)
    try:
        resolve_lang(lang, ALL_LANGS)
    except UnsupportedLanguageError:
        return False
    return True


def _diacritizer_family(lang: str) -> Optional[str]:
    """The diacritizer family of *lang*: ``"he"``, ``"ar"``, ``"stress"``, ``"pt"`` or ``None``.

    ``"stress"`` is any ``STRESS_LANGS`` primary subtag, bare az/uz included,
    as stripping needs no model; :func:`diacritize` narrows it through
    :func:`_is_stress_lang` before it calls stressonnx.
    """
    p = _primary_subtag(lang)
    if p == "he":
        return "he"
    if p in STRESS_LANGS:
        return "stress"
    if _is_european_portuguese(lang):
        return "pt"
    if _is_arabic_script_arabic(lang):
        return "ar"
    return None


#: The package each diacritizer family imports, and the extra that installs it.
_DIACRITIZER_PACKAGES = {
    "he": ("phonikud_onnx", "he"),
    "ar": ("text2tashkeel", "tashkeel"),
    "stress": ("stressonnx", "stress"),
    "pt": ("bifonia", "pt"),
}

_DEFAULT_DIACRITIZER_MODEL = "rawi-ensemble"

_PHONIKUD_CACHE: dict = {}   # resolved model path/string -> Phonikud instance
_TASHKEEL_CACHE: dict = {}  # (model name, waqf) -> text2tashkeel Diacritizer

# A small public model, so scriptconv downloads it on first use.
_PHONIKUD_URL = "https://huggingface.co/thewh1teagle/phonikud-onnx/resolve/main/phonikud-1.0.int8.onnx"


def _default_phonikud_model() -> str:
    """The path of the default phonikud model, downloaded on first use.

    The cache is ``<base>/scriptconv/phonikud``, with ``<base>`` from
    ``$SCRIPTCONV_CACHE``, else ``$XDG_CACHE_HOME``, else ``~/.cache``. The
    download goes to a temporary file that replaces the destination only when
    complete.
    """
    base = os.environ.get("SCRIPTCONV_CACHE") or os.environ.get(
        "XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    cache_dir = Path(base) / "scriptconv" / "phonikud"
    dest = cache_dir / "phonikud-1.0.int8.onnx"
    if not dest.is_file():
        cache_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path = tempfile.mkstemp(dir=str(cache_dir), prefix=".phonikud-", suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as tmp_f, urllib.request.urlopen(_PHONIKUD_URL) as resp:
                while chunk := resp.read(1024 * 1024):
                    tmp_f.write(chunk)
            os.replace(tmp_path, dest)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
    return str(dest)


def _phonikud(phonikud_model=None):
    """The cached phonikud instance of *phonikud_model*: a path, a zero-arg callable that gives one, or ``None`` for the default model."""
    model = phonikud_model() if callable(phonikud_model) else phonikud_model
    if not model:
        model = _default_phonikud_model()
    if model not in _PHONIKUD_CACHE:
        try:
            from phonikud_onnx import Phonikud
        except ImportError:
            raise ImportError(
                "Hebrew diacritization needs phonikud-onnx — install "
                "with `pip install scriptconv[he]`") from None
        _PHONIKUD_CACHE[model] = Phonikud(model)
    return _PHONIKUD_CACHE[model]


#: The ``diacritizer_model`` value that selects Nakdimon for Hebrew.
NAKDIMON = "nakdimon"

# The Nakdimon ONNX model (MIT) at a fixed commit of its repository, and the
# sha256 of the file. The model is 21 MB.
_NAKDIMON_URL = ("https://raw.githubusercontent.com/elazarg/nakdimon/"
                 "5b73cdd6a43ad465faabc8c1118933592df356c8/nakdimon/data/Nakdimon.onnx")
_NAKDIMON_SHA256 = "ab08a8c47daf33886c224859347fa5420c2bfe7ecf4afd2d3387f32b0af12c67"
_NAKDIMON_CACHE: dict = {}  # model path -> Nakdimon


def _nakdimon_path() -> Path:
    """The cache path of the Nakdimon model: ``<base>/scriptconv/nakdimon``, ``<base>`` as for phonikud."""
    base = os.environ.get("SCRIPTCONV_CACHE") or os.environ.get(
        "XDG_CACHE_HOME", os.path.expanduser("~/.cache"))
    return Path(base) / "scriptconv" / "nakdimon" / f"Nakdimon-{_NAKDIMON_SHA256[:12]}.onnx"


def _download_nakdimon(dest: Path, reason: str) -> None:
    """Download the Nakdimon model to *dest* and check its sha256.

    The download goes to a temporary file that replaces *dest* only when its
    sha256 is the pinned one, so no partial or wrong file stays.

    Raises:
        ModelUnavailableError: If the download fails or gives other bytes.
            The message names *dest* and holds *reason*.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=str(dest.parent), prefix=".nakdimon-", suffix=".tmp")
    try:
        digest = hashlib.sha256()
        with os.fdopen(fd, "wb") as tmp_f, urllib.request.urlopen(_NAKDIMON_URL) as resp:
            while chunk := resp.read(1024 * 1024):
                digest.update(chunk)
                tmp_f.write(chunk)
        if digest.hexdigest() != _NAKDIMON_SHA256:
            raise ModelUnavailableError(
                f"the Nakdimon model {dest} {reason}, and the download from {_NAKDIMON_URL} "
                f"has sha256 {digest.hexdigest()}, not {_NAKDIMON_SHA256}")
        os.replace(tmp_path, dest)
    except (urllib.error.URLError, http.client.HTTPException, OSError) as e:
        raise ModelUnavailableError(
            f"the Nakdimon model {dest} {reason}, and it cannot be downloaded from "
            f"{_NAKDIMON_URL}: {e!r}") from e
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _load_nakdimon(path: Path):
    """The Nakdimon diacritizer of the model at *path*, after its sha256 check."""
    import onnxruntime

    from scriptconv.phonemizers._thirdparty.nakdimon import Nakdimon
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != _NAKDIMON_SHA256:
        raise ValueError(f"sha256 {digest}, not {_NAKDIMON_SHA256}")
    return Nakdimon(onnxruntime.InferenceSession(str(path), providers=["CPUExecutionProvider"]))


def _nakdimon_model():
    """The Nakdimon diacritizer of the pinned model, downloaded into the cache on first use.

    The cached file must have the pinned sha256 and load. A file that fails
    is removed and downloaded again once.

    Raises:
        ModelUnavailableError: If no model passes the check, because the
            download fails or the session is offline. The message names the
            file and the cause.
    """
    dest = _nakdimon_path()
    if str(dest) in _NAKDIMON_CACHE:
        return _NAKDIMON_CACHE[str(dest)]
    reason = "is not cached"
    if dest.is_file():
        try:
            _NAKDIMON_CACHE[str(dest)] = _load_nakdimon(dest)
            return _NAKDIMON_CACHE[str(dest)]
        except Exception as e:
            reason = f"fails its check ({e!r}) and was removed"
            LOG.warning("the Nakdimon model %s %s; downloading it again", dest, reason)
            dest.unlink()
    _download_nakdimon(dest, reason)
    try:
        _NAKDIMON_CACHE[str(dest)] = _load_nakdimon(dest)
    except Exception as e:
        raise ModelUnavailableError(f"the Nakdimon model {dest} does not load: {e!r}") from e
    return _NAKDIMON_CACHE[str(dest)]


def _nakdimon(text: str) -> str:
    """*text* with niqqud from Nakdimon.

    Text that holds any vowel point, dagesh, shin or sin dot is returned as
    written: its writer chose the marks. Install onnxruntime with ``pip
    install scriptconv[he]``.
    """
    try:
        import onnxruntime  # noqa: F401

        from scriptconv.phonemizers._thirdparty.nakdimon import remove_niqqud
    except ImportError:
        raise ImportError(
            "Hebrew diacritization with Nakdimon needs onnxruntime and numpy — "
            "install with `pip install scriptconv[he]`") from None
    if remove_niqqud(text) != text:
        return text
    return _nakdimon_model().predict(text)


def _tashkeel(model: Optional[str] = None, waqf: bool = False):
    """The cached text2tashkeel Diacritizer; ``waqf=True`` gives the pausal form, without case and mood endings."""
    model = model or _DEFAULT_DIACRITIZER_MODEL
    key = (model, waqf)
    if key not in _TASHKEEL_CACHE:
        try:
            from text2tashkeel import Diacritizer
        except ImportError as e:
            raise ImportError(
                "Arabic diacritization requires the text2tashkeel package: "
                "pip install scriptconv[tashkeel]  (or pip install text2tashkeel)"
            ) from e
        _TASHKEEL_CACHE[key] = Diacritizer(model, waqf=waqf)
    return _TASHKEEL_CACHE[key]


def _stress(text: str, lang: str, model: Optional[str] = None) -> str:
    """*text* with word stress from stressonnx."""
    try:
        from stressonnx import stress
    except ImportError as e:
        raise ImportError(
            "stress restoration requires the stressonnx package: "
            "pip install scriptconv[stress]  (or pip install stressonnx)"
        ) from e
    return stress(text, lang, model=model)


def _sense_diacritics_pt(text: str, lang: str) -> str:
    """*text* with bifonia's open or closed vowel marks on European-Portuguese homographs, as "sêde" (thirst).

    *lang* goes to bifonia unchanged, so a lect tag reaches its per-lect rows.
    """
    try:
        from bifonia import add_extra_diacritics
    except ImportError as e:
        raise ImportError(
            "European-Portuguese sense diacritics require the bifonia package: "
            "pip install scriptconv[pt]  (or pip install bifonia)"
        ) from e
    return add_extra_diacritics(text, lang)


# The prefix separator that phonikud writes inside a word, after a prefix letter
# and its marks (phonikud_onnx PREFIX_CHAR, phonikud lexicon PREFIX_DIACRITIC).
# A "|" with no Hebrew letter or mark on one side is the writer's, and stays.
_PREFIX_SEPARATOR = re.compile(r"(?<=[\u0591-\u05c7\u05d0-\u05f2])\|(?=[\u05d0-\u05f2])")


def diacritize(text: str, lang: str = "und", diacritizer_model=None,
               waqf: Optional[bool] = None, **kwargs) -> str:
    """Add pronunciation-disambiguating diacritics to *text* for *lang*.

    ``diacritizer_model`` is the model of whichever backend *lang* routes to:

    - Hebrew (``he``): niqqud from phonikud. The model is a phonikud ONNX
      path or a zero-arg callable; without one the public model is downloaded
      and cached. The ``|`` that phonikud writes after a prefix letter
      (``שֶׁ|אֵינָם``) is removed inside a word, so a phonemizer that splits at
      ``|`` keeps the word whole; a ``|`` between words stays.
      ``"nakdimon"`` selects Nakdimon, downloaded the same way; text that
      already holds niqqud stays as written.
    - Arabic in Arabic script (``ar``, ``arz``, ``apc``, Hassaniyya ``mey``):
      tashkeel from text2tashkeel, model name default ``rawi-ensemble``.
      ``waqf=True`` gives the pausal form; other backends ignore ``waqf``.
    - ``STRESS_LANGS``: word stress from stressonnx.
    - European Portuguese (``pt``, ``pt-PT`` and its lects, never ``pt-BR``):
      homograph sense diacritics from bifonia.

    Other languages come back unchanged. A missing backend raises
    ``ImportError`` that names its extra. ``phonikud_model=`` and ``model=``
    are accepted as other names of ``diacritizer_model``.
    """
    diacritizer_model = (diacritizer_model or kwargs.get("phonikud_model")
                         or kwargs.get("model"))
    family = _diacritizer_family(lang)
    if family == "he":
        if diacritizer_model == NAKDIMON:
            return _nakdimon(text)
        return _PREFIX_SEPARATOR.sub("", _phonikud(diacritizer_model).add_diacritics(text))
    if family == "ar":
        return _tashkeel(diacritizer_model, waqf=bool(waqf)).diacritize(text)
    if family == "stress":
        # a bare az/uz, or a script that stressonnx does not write (ru-Latn), never reaches it
        if _is_stress_lang(lang):
            return _stress(text, lang, diacritizer_model)
        return text
    if family == "pt":
        return _sense_diacritics_pt(text, lang)
    return text


# The combining marks each backend overlays on the bare text, which strip removes.
# stressonnx writes the acute; the grave also writes stress, as in Bulgarian.
_STRESS_MARKS = frozenset({0x0300, 0x0301})            # combining grave / acute
_ARABIC_MARKS = frozenset(range(0x064B, 0x0660)) | frozenset({0x0670})  # tashkeel + dagger alef
_HEBREW_MARKS = (frozenset(range(0x05B0, 0x05BE))
                 | frozenset({0x05BF, 0x05C1, 0x05C2, 0x05C4, 0x05C5, 0x05C7}))  # niqqud

# Letters of a stress-family alphabet whose NFD form ends in a stress-mark
# codepoint, by primary subtag. Sources are in the module docstring.
_NATIVE_ACCENTED_LETTERS = {"mk": frozenset("ЃѓЌќ")}


def _overlay_marks(lang: str) -> "frozenset | None":
    """The overlay codepoints of *lang*'s diacritizer family, or None where its marks are spelling or it has none."""
    family = _diacritizer_family(lang)
    if family == "stress":
        return _STRESS_MARKS
    if family == "ar":
        return _ARABIC_MARKS
    if family == "he":
        return _HEBREW_MARKS
    return None


def _supports_strip(lang: str) -> bool:
    """True for languages whose diacritics are removable overlays (stress marks,
    Arabic tashkeel, Hebrew niqqud) rather than native orthography."""
    return _overlay_marks(lang) is not None


def strip_diacritics(text: str, lang: str = "und", **_) -> str:
    """*text* without the overlay diacritics that *lang*'s backend adds; native letters stay.

    A mark that composes with the letter before it into a letter of the
    language's alphabet, as U+0301 after г in NFD ѓ, is kept and written
    composed. Raises :class:`ValueError` where the diacritics are spelling, as
    in European Portuguese, or where the language has no overlay diacritics.
    """
    marks = _overlay_marks(lang)
    if marks is None:
        if _diacritizer_family(lang) == "pt":
            raise ValueError(
                f"cannot strip diacritics for lang={lang!r}: its diacritics are "
                "part of the native orthography, so removal would corrupt the "
                "spelling. strip is defined only for overlay diacritics "
                "(Arabic/Hebrew vocalization, East-Slavic/Turkic stress).")
        raise ValueError(
            f"cannot strip diacritics for lang={lang!r}: scriptconv has no "
            "overlay diacritics for this language. strip is defined only for "
            "overlay diacritics (Arabic/Hebrew vocalization, "
            "East-Slavic/Turkic stress).")
    native = _NATIVE_ACCENTED_LETTERS.get(_primary_subtag(lang), frozenset())
    kept = []
    for c in text:
        if ord(c) not in marks:
            kept.append(c)
            continue
        composed = unicodedata.normalize("NFC", kept[-1] + c) if kept else c
        if composed in native:
            kept[-1] = composed
    return "".join(kept)


# The tags that stressonnx marks (stressonnx/languages/*.json), and the script of each.
_STRESS_SCRIPTS = {
    **dict.fromkeys(("ba", "be", "bg", "cv", "kbd", "kjh", "kk", "ky", "mdf", "mk", "myv", "ru",
                     "sah", "tg", "tt", "udm", "uk", "xal", "az-Cyrl", "uz-Cyrl"), "Cyrl"),
    **dict.fromkeys(("lv", "sl", "az-Latn", "uz-Latn"), "Latn"),
    "hy": "Armn",
    "ka": "Geor",
}
# The vowel letters of each script after which stressonnx writes the mark
# (stressonnx _common.SCRIPT_VOWELS).
_STRESS_VOWELS = {
    "Cyrl": frozenset("\u0430\u0435\u0451\u0438\u043e\u0443\u044b\u044d\u044e\u044f"
                      "\u0456\u0457\u0454\u04d9\u04e9\u04af\u04b1\u04d1\u04d7\u04f3"
                      "\u04e5\u04e7\u045e\u044a\u04e3\u04ef\u04f1"),
    "Latn": frozenset("aeiouy\u00e1\u00e9\u00ed\u00f3\u00fa\u00e0\u00e8\u00ec\u00f2\u00f9"
                      "\u00e2\u00ea\u00ee\u00f4\u00fb\u00e4\u00eb\u00ef\u00f6\u00fc"
                      "\u00e5\u00e6\u00f8\u0153\u00e3\u00f5\u0101\u0113\u012b\u014d\u016b"
                      "\u0259\u0131"),
    "Armn": frozenset("\u0561\u0565\u0567\u0568\u056b\u0578\u0582\u0585"),
    "Geor": frozenset("\u10d0\u10d4\u10d8\u10dd\u10e3"),
}


@functools.lru_cache(maxsize=None)
def _stress_vowels(lang: str) -> frozenset:
    """The vowel letters that carry a stress mark in *lang*, or none for a language stressonnx does not mark.

    linguatag matches *lang* to a stressonnx tag as :meth:`BasePhonemizer.match_lang`
    does, so ``rus`` and ``ukr`` match ``ru`` and ``uk``, and ``kk-Latn`` or
    ``ru-Latn``, a script that stressonnx does not write, matches nothing.
    """
    tag, distance = BasePhonemizer._match_lang(lang, sorted(_STRESS_SCRIPTS))
    return _STRESS_VOWELS[_STRESS_SCRIPTS[tag]] if distance <= 10 else frozenset()


def replace_stress_mark(text: str, lang: str, before: str = "", after: str = "") -> str:
    """*text* with each stress mark (U+0301) that stressonnx can write for *lang* rewritten.

    A stress mark is a U+0301 after a vowel letter of the script that
    stressonnx writes for *lang*. That vowel gets *before* in front of it and
    *after* behind it, in place of the mark, so with neither the mark is
    removed. Any other acute is spelling and stays as written: after a
    consonant, as in NFD Macedonian ѓ and ќ, after a letter of another
    script, as in a Latin ``café`` in Russian text, and in a language that
    stressonnx does not mark. The combining grave (U+0300) stays.
    """
    if STRESS_MARK not in text:
        return text
    vowels = _stress_vowels(lang)
    if not vowels:
        return text
    out = []
    base = None  # where in out the last character that is not a combining mark starts
    for c in text:
        # the first code point of the lowercase form, so that a capital Turkic İ (i + U+0307) counts
        if c == STRESS_MARK and base is not None and out[base].lower()[:1] in vowels:
            out.insert(base, before)
            base += 1
            out.append(after)
            continue
        if not unicodedata.combining(c):
            base = len(out)
        out.append(c)
    return "".join(out)


def register(graph) -> None:
    """Add the ``text <-> text-diacritized`` edges to *graph*.

    Both are ``lossless=False``: the diacritize edge is model-based, and
    :func:`strip_diacritics` maps a marked and a bare letter to one string.
    Pair with :func:`scriptconv.phonemizers.register` to reach
    ``"text-diacritized" -> "ipa"``.
    """
    graph.register(
        Edge("text", DIACRITIZED,
             lambda text, lang="und", diacritizer_model=None, **c:
                 diacritize(text, lang, diacritizer_model=diacritizer_model, **c),
             lossless=False))
    graph.register(
        Edge(DIACRITIZED, "text",
             lambda text, lang="und", **_: strip_diacritics(text, lang),
             lossless=False))
