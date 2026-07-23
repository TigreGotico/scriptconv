"""Diacritization as a graph extension — parallel to :mod:`scriptconv.phonemizers`.

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
from scriptconv.graph import Edge
from scriptconv.phonemizers.base import _diacritizer_family

#: The lang-contextual node produced by diacritization.  Like ``"text"`` it is
#: meaningful only with ``lang=`` context and exists only in opted-in graphs.
DIACRITIZED = "text-diacritized"

_DEFAULT_PHONEMIZER = None


def _get_phonemizer(phonikud_model=None):
    # any concrete BasePhonemizer subclass works here — it's just a vessel
    # for add_diacritics(); GraphemePhonemizer is picked for having no extra
    # runtime dependencies of its own
    global _DEFAULT_PHONEMIZER
    if phonikud_model:
        from scriptconv.phonemizers.base import GraphemePhonemizer
        return GraphemePhonemizer(phonikud_model=phonikud_model)
    if _DEFAULT_PHONEMIZER is None:
        from scriptconv.phonemizers.base import GraphemePhonemizer
        _DEFAULT_PHONEMIZER = GraphemePhonemizer()
    return _DEFAULT_PHONEMIZER


def diacritize(text: str, lang: str = "und", model=None, **context) -> str:
    """Add pronunciation-disambiguating diacritics to *text* for *lang*.

    Thin wrapper over :meth:`BasePhonemizer.add_diacritics` — the single
    dispatch (he→phonikud, ar→tashkeel, ru/uk/be/…→stressonnx, pt→bifonia).
    Reuses a cached default phonemizer so repeated calls don't reload models; a
    per-call Hebrew ``phonikud_model`` path (via context) builds a fresh one.
    """
    return _get_phonemizer(context.get("phonikud_model")).add_diacritics(text, lang, model)


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
    :meth:`BasePhonemizer.add_diacritics` about which language a backend owns.
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
             lambda text, lang="und", model=None, **c: diacritize(text, lang, model, **c),
             lossless=False))
    graph.register(
        Edge(DIACRITIZED, "text",
             lambda text, lang="und", **_: strip_diacritics(text, lang),
             lossless=True))
