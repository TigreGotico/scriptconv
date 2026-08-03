"""Diacritization: mechanism, dispatch, and graph extension.

This module OWNS diacritization — lang→backend routing, lazy/cached backend
loading (phonikud, text2tashkeel, stressonnx, bifonia), and the overlay-strip
helpers. :mod:`scriptconv.phonemizers` (``BasePhonemizer`` and subclasses)
knows nothing about diacritics: phonemization (orthography → sound) and
diacritization (a text → text graph transform disambiguating pronunciation
before G2P) are separate concerns.

Diacritization (Arabic tashkeel, Hebrew niqqud, East-Slavic/Turkic/Caucasian
word stress, European-Portuguese homograph sense marks) is, architecturally,
just another transform between text representations: it maps the ``"text"``
node to a lang-contextual ``"text-diacritized"`` node.  Like
:func:`scriptconv.phonemizers.register` it is opt-in — ``DEFAULT_GRAPH`` stays
free of it until a caller extends a graph::

    from scriptconv.graph import DEFAULT_GRAPH
    from scriptconv import diacritics, phonemizers
    g = DEFAULT_GRAPH.extend(diacritics.register).extend(phonemizers.register)

    g.convert("замок стоит на горе", "text", "text-diacritized", lang="ru")
    # 'за́мок сто́ит на горе́'    — just the diacritized text

    g.convert("Tenho muita sede hoje.", "text", "text-diacritized", lang="pt")
    # 'Tenho muita sêde hoje.'

Routing ``"text" -> "ipa"`` still takes the direct phonemization edge by
default: the diacritization edge is model-based (``lossless=False``), so it
never out-prices a direct phonemization, and enabling this extension does not
silently change phonemization output.  The diacritized route is taken only
when a caller asks for ``"text-diacritized"`` explicitly.

A future per-engine *stance* would push this further into topology rather than
a flag: an engine that *requires* vocalized input would carry only a
``"text-diacritized" -> "ipa"`` edge (forcing the detour), one that *forbids*
diacritics would carry only ``"text" -> "ipa"`` (making the detour
unroutable), and a tolerant engine (e.g. arbtok, which self-vocalizes) carries
both.  The strip direction (``"text-diacritized" -> "text"``) is registered too, but
gated to languages whose marks are removable *overlay* diacritics —
Arabic/Hebrew vocalization and East-Slavic/Turkic/Caucasian stress. Strip
removes only the specific overlay codepoints each backend adds (combining
acute/grave for stress, tashkeel for Arabic, niqqud for Hebrew) — never a
blanket combining-mark filter — so precomposed native letters survive
(Cyrillic й/ё, Latvian macrons, Azerbaijani ç/ö, Arabic hamza carriers أ إ آ ؤ
ئ). The gate uses exact primary-subtag matching, so Aragonese (``arg``),
Herero (``her``), Mapudungun (``arn``) etc. are never misread as Arabic/Hebrew.
Languages whose diacritics are native orthography (European Portuguese, via
bifonia) refuse the strip with :class:`ValueError` instead of silently
corrupting the spelling (``café`` must never become ``cafe``). This split
tracks which backend/model produced the marks: overlay backends (phonikud,
tashkeel, stressonnx) are strippable; spelling-integral backends (bifonia) are
not.
"""
import os
import tempfile
import urllib.request
from pathlib import Path
from typing import Optional

from scriptconv.graph import Edge
from scriptconv.phonemizers.base import _primary_subtag

#: The lang-contextual node produced by diacritization.  Like ``"text"`` it is
#: meaningful only with ``lang=`` context and exists only in opted-in graphs.
DIACRITIZED = "text-diacritized"

# Across East Slavic, Bulgarian/Macedonian/Slovene, Latvian, Armenian,
# Georgian, and several Turkic/Caucasian languages, lexical word stress is
# free (not fixed to a syllable) and ordinary orthography leaves it unwritten
# or under-marked. The clearest case is East Slavic: stress is also mobile
# (it shifts between forms of the same word) and unstressed vowels *reduce*
# — Russian unstressed "о" surfaces as [ɐ] or [ə] depending on distance from
# the stress, not [o] — so a wrong or missing mark there corrupts the vowel
# quality of the whole word, not just its prosody. Other families in this set
# don't necessarily reduce vowels, but still need the mark for correct stress
# placement and prosody. stressonnx restores it as a combining acute (U+0301)
# after the stressed vowel, covering 26 BCP-47 tags across these families
# (24 primary subtags; Azerbaijani and Uzbek each have Cyrillic/Latin script
# variants routed by the full tag).
STRESS_LANGS = {
    "az", "ba", "be", "bg", "cv", "hy", "ka", "kbd", "kjh", "kk", "ky", "lv",
    "mdf", "mk", "myv", "ru", "sah", "sl", "tg", "tt", "udm", "uk", "uz", "xal",
}


def _is_european_portuguese(lang: str) -> bool:
    """True for European Portuguese (``pt`` or a ``pt-PT`` region tag).

    False for Brazilian Portuguese (``pt-BR``) and everything else — the two
    varieties' vowel systems differ, and bifonia's open/closed diacritics are
    only valid for European Portuguese phonology.
    """
    norm = lang.lower().replace("_", "-")
    return norm == "pt" or norm == "pt-pt"


def _diacritizer_family(lang: str) -> Optional[str]:
    """Which diacritization backend family handles *lang*, or ``None``.

    Single source of truth for lang→backend routing: both the forward
    dispatch (:func:`diacritize`) and the strip direction (:func:`_overlay_marks`)
    resolve through this, so the two can never disagree about which language
    uses which backend. Returns one of ``"he"`` (niqqud), ``"ar"`` (tashkeel),
    ``"stress"`` (stressonnx), ``"pt"`` (bifonia sense diacritics), or
    ``None``. Uses exact primary-subtag matching (never ``startswith``), so
    Aragonese (``arg``), Herero (``her``) and Mapudungun (``arn``) are never
    misread as Arabic/Hebrew.
    """
    p = _primary_subtag(lang)
    if p == "he":
        return "he"
    if p == "ar":
        return "ar"
    if p in STRESS_LANGS:
        return "stress"
    if _is_european_portuguese(lang):
        return "pt"
    return None


_DEFAULT_DIACRITIZER_MODEL = "rawi-ensemble"

_PHONIKUD_CACHE: dict = {}   # resolved model path/string -> Phonikud instance
_TASHKEEL_CACHE: dict = {}  # model name -> text2tashkeel Diacritizer

# phonikud is a small (~100MB), public, unlicensed-restriction ONNX model, so
# — unlike the large/licensed models behind mul.py's ByT5/Charsiu backends —
# scriptconv auto-provisions it: no local path is required unless the caller
# wants to override the cache (e.g. an air-gapped host).
_PHONIKUD_URL = "https://huggingface.co/thewh1teagle/phonikud-onnx/resolve/main/phonikud-1.0.int8.onnx"


def _default_phonikud_model() -> str:
    """Resolve (downloading and caching on first use if needed) the path to
    the default phonikud ONNX model.

    Cache directory: ``<base>/scriptconv/phonikud`` where ``<base>`` is
    ``$SCRIPTCONV_CACHE`` if set, else ``$XDG_CACHE_HOME`` (default
    ``~/.cache``) — i.e. ``~/.cache/scriptconv/phonikud`` by default. The
    download is written to a temp file
    in the same directory and atomically moved into place via
    :func:`os.replace`, so a failed or interrupted download never leaves a
    partial file at the destination path.
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
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    tmp_f.write(chunk)
            os.replace(tmp_path, dest)
        except BaseException:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
    return str(dest)


def _phonikud(phonikud_model=None):
    """Lazily build (and cache) the phonikud Phonikud instance used for Hebrew.

    ``phonikud_model`` is optional: a local path to a phonikud ONNX model, or
    a zero-arg callable resolving one lazily. When omitted, scriptconv
    auto-provisions the small public phonikud model, downloading it once into
    a cache dir (see :func:`_default_phonikud_model`) and reusing it on
    subsequent calls. Pass an explicit path/callable to override — e.g. to
    point at a model already on disk, or on an air-gapped host. Install
    phonikud-onnx with ``pip install scriptconv[he]`` (or ``pip install
    phonikud-onnx``)."""
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


def _tashkeel(model: Optional[str] = None):
    """Lazily build (and cache) the text2tashkeel Diacritizer used for Arabic.

    text2tashkeel is a dependency of the ``[ar]`` extra; it restores hamza and the
    dagger alef in addition to the standard marks. Install with
    ``pip install scriptconv[tashkeel]`` (or ``pip install text2tashkeel``)."""
    model = model or _DEFAULT_DIACRITIZER_MODEL
    if model not in _TASHKEEL_CACHE:
        try:
            from text2tashkeel import Diacritizer
        except ImportError as e:
            raise ImportError(
                "Arabic diacritization requires the text2tashkeel package: "
                "pip install scriptconv[tashkeel]  (or pip install text2tashkeel)"
            ) from e
        _TASHKEEL_CACHE[model] = Diacritizer(model)
    return _TASHKEEL_CACHE[model]


def _stress(text: str, lang: str, model: Optional[str] = None) -> str:
    """Word-stress restoration via stressonnx, for the 26 language tags
    it covers (see ``STRESS_LANGS``) — East Slavic, Bulgarian/Macedonian/
    Slovene, Latvian, Armenian, Georgian, and Turkic/Caucasian languages.

    stressonnx is not on PyPI yet; install straight from source. Install
    with ``pip install scriptconv[stress]`` (or ``pip install
    stressonnx``)."""
    try:
        from stressonnx import stress
    except ImportError as e:
        raise ImportError(
            "stress restoration requires the stressonnx package: "
            "pip install scriptconv[stress]  (or pip install stressonnx)"
        ) from e
    return stress(text, lang, model=model)


def _sense_diacritics_pt(text: str) -> str:
    """European-Portuguese heterophonic-homograph sense diacritics via bifonia.

    Rewrites homographs whose pronunciation depends on meaning (e.g.
    "sede" thirst/closed vs. seat/open) with an explicit open/closed
    vowel diacritic. These are ordinary Portuguese orthographic marks,
    chosen so any downstream G2P — rule-based, neural, or espeak —
    reads them correctly. Install with ``pip install scriptconv[pt]``
    (or ``pip install bifonia``)."""
    try:
        from bifonia import add_extra_diacritics
    except ImportError as e:
        raise ImportError(
            "European-Portuguese sense diacritics require the bifonia package: "
            "pip install scriptconv[pt]  (or pip install bifonia)"
        ) from e
    return add_extra_diacritics(text)


def diacritize(text: str, lang: str = "und", diacritizer_model=None,
               **kwargs) -> str:
    """Add pronunciation-disambiguating diacritics to *text* for *lang*.

    ``diacritizer_model=`` is the one model knob for the diacritizer edge — the
    model for whichever backend the language routes to (there is one such knob,
    parallel to ``phonemizer_model=`` on the ``text -> ipa`` phonemizer edge):

    - Hebrew (``he``) — niqqud via phonikud; ``diacritizer_model`` is the
      phonikud ONNX path (or a zero-arg callable). Optional: when omitted the
      small public phonikud model is auto-downloaded and cached
      (``$SCRIPTCONV_CACHE``/``$XDG_CACHE_HOME``).
    - Arabic (``ar``) — tashkeel via text2tashkeel (``[tashkeel]``);
      ``diacritizer_model`` is the text2tashkeel model name (defaults to
      ``rawi-ensemble``).
    - East Slavic, Bulgarian/Macedonian/Slovene, Latvian, Armenian, Georgian,
      and Turkic/Caucasian languages (``STRESS_LANGS``, 26 stressonnx tags) —
      word stress via stressonnx (``[stress]``); ``diacritizer_model`` is the
      stressonnx model. Stress is unwritten or under-marked in these languages,
      and in East Slavic unstressed vowels also reduce, so a missing mark can
      corrupt more than prosody.
    - European Portuguese (``pt``/``pt-PT``, never ``pt-BR``) —
      heterophonic-homograph sense diacritics via bifonia (``[pt]``);
      ordinary Portuguese orthographic marks that any downstream G2P reads
      correctly.

    Unrecognized languages are returned unchanged. Each backend raises
    ``ImportError`` naming its extra when the optional dependency is missing
    — scriptconv never installs anything on the caller's behalf.
    """
    # one knob for the diacritizer edge; fold the pre-unification kwargs so
    # older callers keep working (phonikud_model was the Hebrew-only name).
    diacritizer_model = (diacritizer_model or kwargs.get("phonikud_model")
                         or kwargs.get("model"))
    family = _diacritizer_family(lang)
    if family == "he":
        return _phonikud(diacritizer_model).add_diacritics(text)
    if family == "ar":
        return _tashkeel(diacritizer_model).diacritize(text)
    if family == "stress":
        return _stress(text, lang, diacritizer_model)
    if family == "pt":
        return _sense_diacritics_pt(text)
    return text


# Combining marks each diacritization backend overlays onto the bare text.
# Strip removes ONLY these codepoints — never a blanket combining-mark filter,
# which (via NFD) would decompose and destroy precomposed native letters:
# Cyrillic й/ё, Latvian ī, Azerbaijani ç/ö, and Arabic hamza carriers أ إ آ ؤ ئ.
_STRESS_MARKS = frozenset({0x0300, 0x0301})            # combining grave / acute
# U+0300 is included defensively alongside the U+0301 that stressonnx
# actually emits, in case any backend/locale marks secondary stress with a
# grave instead of an acute; harmless to strip since native precomposed
# letters (e.g. Cyrillic й/ё) are unaffected either way.
_ARABIC_MARKS = frozenset(range(0x064B, 0x0660)) | frozenset({0x0670})  # tashkeel + dagger alef
_HEBREW_MARKS = (frozenset(range(0x05B0, 0x05BE))
                 | frozenset({0x05BF, 0x05C1, 0x05C2, 0x05C4, 0x05C5, 0x05C7}))  # niqqud


def _overlay_marks(lang: str) -> "frozenset | None":
    """The overlay codepoints for *lang*'s diacritization backend, or None.

    Resolves the backend family through :func:`_diacritizer_family` (the shared
    lang→backend routing), so this can never disagree with
    :func:`diacritize` about which language a backend owns.
    Only *overlay* families are strippable: ``"pt"`` (bifonia sense marks are
    native orthography) and ``None`` both return None.
    """
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
    """Remove the overlay diacritics *lang*'s backend adds, recovering the bare
    text WITHOUT touching native letters.

    Removes only the specific overlay codepoints (combining acute/grave for
    stress, tashkeel for Arabic, niqqud for Hebrew) — precomposed native
    letters (Cyrillic й/ё, Latvian ī, Azerbaijani ç, Arabic hamza carriers) are
    left intact. Raises :class:`ValueError` for languages whose diacritics are
    part of the native orthography (e.g. European Portuguese), where any removal
    would corrupt the spelling.
    """
    marks = _overlay_marks(lang)
    if marks is None:
        raise ValueError(
            f"cannot strip diacritics for lang={lang!r}: its diacritics are "
            "part of the native orthography, so removal would corrupt the "
            "spelling. strip is defined only for overlay diacritics "
            "(Arabic/Hebrew vocalization, East-Slavic/Turkic stress).")
    return "".join(c for c in text if ord(c) not in marks)


def register(graph) -> None:
    """Opt-in graph integration: add the diacritize/strip edge pair.

    ``text -> text-diacritized`` is model-based (``lossless=False``), so a
    direct ``text -> ipa`` phonemization always out-prices the detour —
    enabling this extension is safe and non-invasive.  Pair with
    :func:`scriptconv.phonemizers.register` to make
    ``"text-diacritized" -> "ipa"`` reachable.

    ``text-diacritized -> text`` (:func:`strip_diacritics`) is lossless and
    cheap, but gated: it raises for languages whose diacritics are native
    orthography rather than removable overlays.
    """
    graph.register(
        Edge("text", DIACRITIZED,
             lambda text, lang="und", diacritizer_model=None, **c:
                 diacritize(text, lang, diacritizer_model=diacritizer_model, **c),
             lossless=False))
    graph.register(
        Edge(DIACRITIZED, "text",
             lambda text, lang="und", **_: strip_diacritics(text, lang),
             lossless=True))
