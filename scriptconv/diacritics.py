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
both.  The strip direction (``"text-diacritized" -> "text"``) is registered
too, but gated to languages whose marks are removable *overlay* diacritics —
Arabic/Hebrew vocalization and East-Slavic/Turkic/Caucasian stress, whose bare
canonical form carries no marks, so stripping every combining mark recovers it
losslessly.  Languages whose diacritics are native orthography (European
Portuguese, via bifonia) refuse the strip with :class:`ValueError` instead of
silently corrupting the spelling (``café`` must never become ``cafe``).  This
split tracks which backend/model produced the marks: overlay backends
(phonikud, tashkeel, stressonnx) are strippable; spelling-integral backends
(bifonia) are not.
"""
import unicodedata

from scriptconv.graph import Edge
from scriptconv.phonemizers.base import STRESS_LANGS, _primary_subtag

#: The lang-contextual node produced by diacritization.  Like ``"text"`` it is
#: meaningful only with ``lang=`` context and exists only in opted-in graphs.
DIACRITIZED = "text-diacritized"


def diacritize(text: str, lang: str = "und", model=None, **context) -> str:
    """Add pronunciation-disambiguating diacritics to *text* for *lang*.

    Thin wrapper over :meth:`BasePhonemizer.add_diacritics` — the single
    dispatch that routes he→phonikud, ar→tashkeel, ru/uk/be/…→stressonnx,
    pt→bifonia. A Hebrew ``phonikud_model`` path may be supplied via context.
    """
    from scriptconv.phonemizers.base import GraphemePhonemizer
    phonemizer = GraphemePhonemizer(phonikud_model=context.get("phonikud_model"))
    return phonemizer.add_diacritics(text, lang, model)


def _supports_strip(lang: str) -> bool:
    """True for overlay-diacritic languages whose bare form carries no marks.

    Arabic/Hebrew vocalization and East-Slavic/Turkic/Caucasian stress are
    removable overlays — stripping every combining mark recovers the bare
    text losslessly.  European Portuguese (bifonia) is excluded: its marks are
    native orthography, so stripping would corrupt the spelling.
    """
    return (_primary_subtag(lang) in STRESS_LANGS
            or lang.lower().startswith(("he", "ar")))


def strip_diacritics(text: str, lang: str = "und", **_) -> str:
    """Remove overlay diacritics, recovering the bare text.

    Defined only for overlay-diacritic languages (see :func:`_supports_strip`);
    raises :class:`ValueError` for languages whose diacritics are part of the
    native orthography (e.g. Portuguese), where removal would corrupt spelling.
    """
    if not _supports_strip(lang):
        raise ValueError(
            f"cannot strip diacritics for lang={lang!r}: its diacritics are "
            "part of the native orthography, so removal would corrupt the "
            "spelling. strip is defined only for overlay diacritics "
            "(Arabic/Hebrew vocalization, East-Slavic/Turkic stress).")
    return unicodedata.normalize(
        "NFC", "".join(c for c in unicodedata.normalize("NFD", text)
                       if not unicodedata.combining(c)))


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
