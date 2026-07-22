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
both.  The strip direction (``"text-diacritized" -> "text"``) is deliberately
not registered here: removing marks is a clean lossless inverse for overlay
diacritics (Arabic harakat, Cyrillic stress) but not for languages where the
marks are native orthography (Portuguese), so a universal strip edge would
corrupt them.
"""
from scriptconv.graph import Edge

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


def register(graph) -> None:
    """Opt-in graph integration: add the ``text -> text-diacritized`` edge.

    The edge is model-based (``lossless=False``), so a direct ``text -> ipa``
    phonemization always out-prices the detour — enabling this extension is
    safe and non-invasive.  Pair with :func:`scriptconv.phonemizers.register`
    to make ``"text-diacritized" -> "ipa"`` reachable.
    """
    graph.register(
        Edge("text", DIACRITIZED,
             lambda text, lang="und", model=None, **c: diacritize(text, lang, model, **c),
             lossless=False))
