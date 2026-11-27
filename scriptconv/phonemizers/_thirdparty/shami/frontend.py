"""The unified text front-end: ``str -> (phoneme_ids, language_ids)``.

Ported from hams_tts.text.frontend (Apache-2.0).  With ``inventory=90`` the front end
also reads pauses from punctuation, as upstream commit 80d79d0 does: a run of
``, ; :`` becomes ``sil`` and a run that holds ``. ! … —`` becomes ``brk``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .codeswitch import Span, segment
from .diacritize import get_diacritizer, is_already_diacritized
from .english_g2p import english_g2p
from .levantine_g2p import arabic_fallback_ipa, levantine_g2p
from .normalize import normalize_unicode
from .phoneme_inventory import (
    BOS,
    BRK,
    EOS,
    PUNCT,
    SIL,
    SYL_SEP,
    WORD_SEP,
    Lang,
    get_inventory,
)

_PUNCT_SET = set(PUNCT)

_PAUSE_RE = re.compile(r"[,.!;:\u2026\u2014]+")
_SHORT_PAUSE = {",", ";", ":"}


def _split_pauses(text: str) -> List[Tuple[str, str]]:
    """Split *text* into ``("text", chunk)`` and ``("pause", SIL | BRK)`` parts, in order.

    A run of pause marks is one pause; a run that holds a sentence mark is ``BRK``.
    """
    parts: List[Tuple[str, str]] = []
    last = 0
    for m in _PAUSE_RE.finditer(text):
        if m.start() > last:
            parts.append(("text", text[last:m.start()]))
        parts.append(("pause", SIL if set(m.group()) <= _SHORT_PAUSE else BRK))
        last = m.end()
    if last < len(text):
        parts.append(("text", text[last:]))
    return parts


@dataclass
class Utterance:
    """Everything downstream stages needs, plus debug breadcrumbs."""

    text: str
    normalized: str
    ipa: str
    symbols: List[str]
    phoneme_ids: List[int]
    language_ids: List[int]
    spans: List[Span] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.phoneme_ids)

    def pretty(self) -> str:
        rows = [f"text       : {self.text}", f"normalized : {self.normalized}", f"ipa        : {self.ipa}"]
        rows.append("tokens     : " + " ".join(self.symbols))
        rows.append("lang_ids   : " + " ".join(Lang(lid).name[0] if lid in (1, 2) else "·" for lid in self.language_ids))
        return "\n".join(rows)


class TextFrontend:
    """Text to the phoneme and language-ID streams of a ShamiVITS model.

    ``inventory`` is the symbol count of the model the ids are for: 88 for the
    single-speaker models, 90 for the multi-speaker models with ``sil`` and ``brk``.

    Raises:
        ValueError: If ``inventory`` is not 88 or 90.
    """

    def __init__(
        self,
        diacritizer_backend: str = "auto",
        default_lang: str = "en",
        back_emphatics: bool = True,
        epenthesize: bool = True,
        dialectal_case_drop: bool = True,
        inventory: int = 88,
    ) -> None:
        self.inventory = get_inventory(inventory)
        self.pauses = SIL in self.inventory.symbol_to_id
        self.default_lang = default_lang
        self.back_emphatics = back_emphatics
        self.epenthesize = epenthesize
        self.dialectal_case_drop = dialectal_case_drop
        self._diacritizer = get_diacritizer(diacritizer_backend)
        self.diacritizer_backend = diacritizer_backend
        self.has_diacritizer = self._diacritizer is not None

    def _arabic_to_ipa(self, text: str) -> str:
        if is_already_diacritized(text):
            diac = text
        elif self._diacritizer is not None:
            diac = self._diacritizer(text)
        else:
            return arabic_fallback_ipa(text, self.back_emphatics, self.inventory)
        if self.dialectal_case_drop:
            from .dialectal import strip_case_endings
            diac = strip_case_endings(diac)
        return levantine_g2p(diac, self.back_emphatics, self.epenthesize)

    def _span_to_ipa(self, span: Span) -> str:
        if span.lang == "ar":
            return self._arabic_to_ipa(span.text)
        return english_g2p(span.text, self.inventory)

    def process(self, text: str) -> Utterance:
        normalized = normalize_unicode(text)
        spans = segment(normalized, default_lang=self.default_lang)

        symbols: List[str] = [BOS]
        language_ids: List[int] = [int(Lang.PAD)]
        ipa_parts: List[str] = []

        def emit_neutral(symbol: str) -> None:
            symbols.append(symbol)
            language_ids.append(int(Lang.NEUTRAL))

        def emit_span(span: Span) -> None:
            ipa = self._span_to_ipa(span)
            ipa_parts.append(ipa)
            span_lang = Lang.AR if span.lang == "ar" else Lang.EN
            for s in self.inventory.tokenize(ipa).symbols:
                symbols.append(s)
                if s in _PUNCT_SET or s in (WORD_SEP, SYL_SEP):
                    language_ids.append(int(Lang.NEUTRAL))
                else:
                    language_ids.append(int(span_lang))

        if self.pauses:
            prev_pause = False  # a pause takes the place of the next word boundary
            for idx, span in enumerate(spans):
                for p_idx, (kind, value) in enumerate(_split_pauses(span.text)):
                    if kind == "pause":
                        emit_neutral(value)
                        prev_pause = True
                        continue
                    if not value.strip():
                        continue
                    if p_idx > 0 or (idx > 0 and not prev_pause):
                        emit_neutral(WORD_SEP)
                    prev_pause = False
                    emit_span(Span(value, span.lang))
        else:
            for idx, span in enumerate(spans):
                if idx > 0:
                    emit_neutral(WORD_SEP)
                emit_span(span)

        symbols.append(EOS)
        language_ids.append(int(Lang.PAD))

        phoneme_ids = [self.inventory.symbol_to_id[s] for s in symbols]
        ipa = "  ".join(ipa_parts)
        assert len(phoneme_ids) == len(language_ids) == len(symbols)
        return Utterance(
            text=text,
            normalized=normalized,
            ipa=ipa,
            symbols=symbols,
            phoneme_ids=phoneme_ids,
            language_ids=language_ids,
            spans=spans,
        )

    __call__ = process


_DEFAULT: Optional[TextFrontend] = None


def get_default_frontend() -> TextFrontend:
    global _DEFAULT
    if _DEFAULT is None:
        _DEFAULT = TextFrontend()
    return _DEFAULT
