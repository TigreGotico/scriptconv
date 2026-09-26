import re
from typing import Optional

from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.base import BasePhonemizer, _check_alphabet


# Module-level indirection for the mantoq backend: resolved lazily on first
# construction, kept as module globals so tests and callers can patch them.
mantoq = None  # the g2p callable
_halabi_backend = None  # (arabic_to_buckwalter, process_utterance) tuple
_iqra_backend = None  # (arabic_to_buckwalter, process_utterance) tuple, IqraEval fork
from scriptconv.notation import halabi_to_ipa, iqra_halabi_to_ipa  # noqa: E402  (patchable names)


def _load_mantoq_g2p():
    try:
        # an externally-installed upstream mantoq wins
        import mantoq as _pkg
    except ImportError:
        # quarantined vendored copy under its OWN license (the phonetisation
        # core is CC BY-NC 4.0 — see _vendored/mantoq/LICENSE.md); using it
        # is an explicit opt-in by requesting this phonemizer
        from scriptconv.phonemizers import _vendored
        from scriptconv.phonemizers._vendored import mantoq as _pkg
    return _pkg.g2p


def _load_halabi_backend():
    """Resolve ``(arabic_to_buckwalter, process_utterance)`` — the raw Halabi
    phonetiser, one layer below mantoq's own diacritizer + tokenizer.  Same
    lazy, externally-installed-package-first, quarantined-vendored-copy-
    fallback pattern as :func:`_load_mantoq_g2p` — one import path, three
    edges (:class:`MantoqPhonemizer`, :class:`HalabiPhonemizer`,
    :class:`IqraPhonemizer`) share it.
    """
    try:
        from mantoq.buck.phonetise_buckwalter import (
            arabic_to_buckwalter, process_utterance)
    except ImportError:
        from scriptconv.phonemizers import _vendored
        from scriptconv.phonemizers._vendored.mantoq.buck.phonetise_buckwalter import (
            arabic_to_buckwalter, process_utterance)
    return arabic_to_buckwalter, process_utterance


def _load_iqra_backend():
    """Resolve ``(arabic_to_buckwalter, process_utterance)`` from the
    IqraEval shared task's OWN published data-prep code
    (Iqra-Eval/MSA_phonetiser's ``phonetiser/phonetise_Arabic.py``), vendored
    separately from :func:`_load_halabi_backend`'s mantoq copy — see
    ``_vendored/iqra_phonetiser/LICENSE.md`` and ``phonetiser.py``'s module
    docstring for why the two diverge and what each patch fixes.  Only
    :class:`IqraPhonemizer` uses this; :class:`HalabiPhonemizer` and
    :class:`MantoqPhonemizer` keep the long-standing mantoq-derived backend.
    """
    from scriptconv.phonemizers import _vendored
    from scriptconv.phonemizers._vendored.iqra_phonetiser.phonetiser import (
        arabic_to_buckwalter, process_utterance)
    return arabic_to_buckwalter, process_utterance


# Raw Halabi phonetiser output carries a vowel-realization digit suffix
# (i0/i1, u0/u1, ii0/ii1, ...) that mantoq's own g2p strips before a caller
# ever sees it (mantoq/buck/tokenization.py's ``vowel_map``); the two raw
# edges below strip it the same way for IPA output / IqraEval post-processing.
_HALABI_STRESS_DIGIT_RE = re.compile(r"([A-Za-z]+)[012]\b")


def _strip_halabi_digits(raw: str) -> str:
    return _HALABI_STRESS_DIGIT_RE.sub(r"\1", raw)


# ---------------------------------------------------------------------------
# IqraEval text-level pre-processing: three deterministic, dataset-verified
# transforms applied to the DIACRITIZED input text before it reaches the
# Halabi phonetiser, so its own rules produce the IqraEval phoneme_ref
# convention without needing to touch the phonetiser itself. Verified against
# a 2,588-row held-out sample of IqraEval/Iqra_train's dev split (see the PR
# description for the methodology and the exact-match rate); each rule is
# cited to its tajwid/grammar name.
#
# 1. Tanwīn (nunation — fatḥ/ḍamm/kasr) is dropped everywhere, not just at a
#    pause: this dataset's reference never represents the nasalized /n/ of
#    nunation (real recitation would assimilate it into the next letter per
#    nūn sākinah/tanwīn rules — idghām, iqlāb, ikhfā', iẓhār — depending on
#    context; the reference instead simply omits it throughout).
_TANWIN_RE = re.compile("[ًٌٍ]")  # fatḥatān/ḍammatān/kasratān

# 2. Wāw al-jamāʿah: the plural-verb ending spelled "-ūā" (ḍamma + و + ا) is
#    read /-ū/ — the trailing alif is a purely orthographic marker (the
#    "alif al-fāṣila"), never pronounced. The raw phonetiser (lacking this
#    orthographic convention) reads the alif as a genuine short /a/ after the
#    /w/; drop it before phonetisation.
_WAW_JAMAA_RE = re.compile("(و)ا(?=[\\s.!?,،؛؟]|$)")

# 3. Ibtidā' bi-hamzat al-waṣl: the connecting hamza of the definite article
#    "ال" is silent mid-utterance (waṣl) but MUST be pronounced, with fatḥa,
#    the moment recitation starts on it (Ibn al-Jazarī, al-Muqaddimah,
#    bāb hamzat al-waṣl). The Halabi phonetiser has no utterance-position
#    awareness, so an utterance-initial "ال" is rewritten to an explicit
#    hamza (أَ) before phonetisation.
_INITIAL_AL_RE = re.compile("^ا(?=ل)")


def _iqra_preprocess(text: str) -> str:
    text = _TANWIN_RE.sub("", text)
    text = _WAW_JAMAA_RE.sub(r"\1", text)
    text = _INITIAL_AL_RE.sub("أَ", text)
    text = _pausal_last_word(text)
    return text


#: A phrase ends at sentence punctuation or at the end of the string — the
#: same split arbtok's ``waqf.pausal(..., phrase_final_only=True)`` uses.
_PHRASE_RE = re.compile("[^.!?،؛؟…\n]+|[.!?،؛؟…\n]+")
_PUNCT = frozenset(".!?،؛؟…\n")
_WORD_RE = re.compile("[ء-ٰٱ-ۓ]+")
_TRAILING_MARKS_RE = re.compile("[ً-ْٰ]+$")
_SHORT_VOWELS = ("َ", "ُ", "ِ")  # fatḥa, ḍamma, kasra
_KEPT_MARKS = ("ْ", "ّ")  # sukūn, shadda


def _pausal_word(word: str) -> str:
    """Drop a word's final short vowel (its iʿrāb case/mood ending) — waqf.

    Minimal port of arbtok's (TigreGotico/arbtok, Apache-2.0, itself vendored
    from ``text2tashkeel.waqf``) ``_pausal_word``; ``pausal()``'s tanwīn
    handling is not needed here since :data:`_TANWIN_RE` already stripped
    every tanwīn mark before this runs.
    """
    marks = _TRAILING_MARKS_RE.search(word)
    if not marks:
        return word
    tail = marks.group()
    if any(v in tail for v in _SHORT_VOWELS):
        return word[: marks.start()] + "".join(c for c in tail if c in _KEPT_MARKS)
    return word


def _pausal_last_word(text: str) -> str:
    """Apply :func:`_pausal_word` to the last Arabic word of each phrase only
    — mid-phrase words keep their case endings (waṣl); only the word at an
    actual pause drops its ending, matching how the IqraEval reference reads
    continuous recitation.
    """
    out = []
    for chunk in _PHRASE_RE.findall(text):
        if chunk and chunk[0] in _PUNCT:
            out.append(chunk)
            continue
        words = list(_WORD_RE.finditer(chunk))
        if not words:
            out.append(chunk)
            continue
        last = words[-1]
        out.append(chunk[: last.start()] + _pausal_word(last.group())
                   + chunk[last.end():])
    return "".join(out)


class MantoqPhonemizer(BasePhonemizer):
    """Arabic phonemizer backed by mantoq (Halabi Arabic-Phonetiser pipeline).

    Distributed under its own license from the quarantined vendored copy —
    the phonetisation core is CC BY-NC 4.0, non-commercial — unless an
    externally-installed ``mantoq`` package is present.  Never selected
    automatically; :class:`ArbtokPhonemizer` is the Arabic default.

    Historical contract, preserved for models in the wild: the default
    ``alphabet=Alphabet.BUCKWALTER`` returns the raw mantoq inventory (its
    long-standing, if imprecise, label — ``Alphabet.HALABI`` is the accurate
    alias); ``Alphabet.IPA`` converts via
    :func:`scriptconv.notation.halabi_to_ipa`.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.BUCKWALTER):
        if alphabet not in (Alphabet.IPA, Alphabet.BUCKWALTER, Alphabet.HALABI):
            raise ValueError("unsupported alphabet")
        super().__init__(alphabet)
        global mantoq
        if mantoq is None:
            mantoq = _load_mantoq_g2p()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["ar"])

    def phonemize_string(self, text: str, lang: str = "ar") -> str:
        """Phonemize Arabic text via mantoq's G2P.

        Tokens are joined and the ``_+_`` word separator becomes a space —
        the byte-exact historical behavior; IPA output converts the joined
        string with :func:`halabi_to_ipa`.
        """
        lang = self.get_lang(lang)
        normalized_text, phonemes = mantoq(text)
        phonemes = "".join(phonemes).replace("_+_", " ")
        if self.alphabet == Alphabet.IPA:
            return halabi_to_ipa(phonemes)
        return phonemes



class ArbtokPhonemizer(BasePhonemizer):
    """
    Arabic phonemizer backed by ``arbtok``, an engine built on the
    orthography2ipa lattice.  Its edge over bare orthography2ipa is
    **undiacritized** Arabic: ``arbtok`` restores the tashkeel with a bundled
    diacritizer before transcribing, so it reads the unvocalized text people
    actually type.  Output is always IPA.

    The variety is any orthography2ipa Arabic spec code (``ar``, ``arb``,
    ``ar-EG``, ``ar-SA-x-najd``, ...), taken from the per-call ``lang`` argument.

    Register: arbtok's own default is the pausal (spoken) register, which is the
    right choice for the dialects; the full iʿrāb register is only phonologically
    apt for ``ar``/``arb`` (MSA/Classical).  The default here defers to arbtok's
    register default rather than overriding it, so this convention lives in the
    engine; pass ``model`` of ``"i'rab"`` to force the full register.

    ``arbtok`` is imported lazily so importing ``scriptconv`` does not hard-require it.
    """

    def __init__(self, register: Optional[str] = None,
                 alphabet: Alphabet = Alphabet.IPA):
        if alphabet != Alphabet.IPA:
            raise ValueError("arbtok only outputs IPA")
        # register: None -> defer to arbtok's own default (pausal). The iʿrab
        # aliases force arbtok's full case-ending register, which the plugin
        # spells "full" (apt only for ar/arb); pass any other value through so a
        # caller can still say "pausal"/"full" directly.
        self.register = None
        if register:
            self.register = ("full" if register.lower() in ("irab", "i'rab", "iʿrab", "full")
                             else register)
        self._cache = {}
        super().__init__(alphabet)

    def _engine(self, lang: str):
        """Return, lazily creating and caching, the arbtok engine for *lang*."""
        key = (lang, self.register)
        if key not in self._cache:
            try:
                from arbtok.plugin import ArbtokG2PPlugin
            except ImportError as e:
                raise ImportError(
                    "arbtok is required for the arbtok Arabic phonemizer. "
                    "Install it with 'pip install arbtok' "
                    "(or 'pip install scriptconv[ar-phonemizers]')."
                ) from e
            kwargs = dict(lang=lang, diacritize=True)
            if self.register is not None:
                kwargs["register"] = self.register
            self._cache[key] = ArbtokG2PPlugin(**kwargs)
        return self._cache[key]

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Resolve *target_lang* to an arbtok/orthography2ipa Arabic spec code.

        Raises:
            ValueError: If arbtok has no Arabic variety for *target_lang*.
        """
        try:
            from arbtok import spec_for_lang
        except ImportError as e:
            raise ImportError(
                "arbtok is required for the arbtok Arabic phonemizer. "
                "Install it with 'pip install arbtok' (or 'pip install scriptconv[ar-phonemizers]')."
            ) from e
        return spec_for_lang(target_lang)

    def phonemize_string(self, text: str, lang: str = "ar") -> str:
        return self._engine(self.get_lang(lang)).transcribe(text)


class HalabiPhonemizer(BasePhonemizer):
    """Raw Halabi Arabic-Phonetiser edge — the rule engine itself, no
    diacritizer in front of it.

    **Input contract: already-vowelized (fully ``tashkeel``'d) Arabic text.**
    This calls the phonetiser directly (``arabic_to_buckwalter`` +
    ``process_utterance``, the same two calls :class:`MantoqPhonemizer` makes
    after its own diacritizer runs) — bare/undiacritized text is garbage in,
    garbage out, matching upstream: the rule set reads the diacritics on the
    page, it does not restore them. Use :class:`MantoqPhonemizer` (or
    :class:`ArbtokPhonemizer`) for undiacritized input.

    ``Alphabet.HALABI`` (default) is the native raw notation, verbatim: the
    stress/vowel-realization digit suffix (``i0``/``i1``/``u0``/``u1``/…),
    the emphatic-context uppercase vowels (``A``/``AA``/``I``/``II``/``U``/
    ``UU``) mantoq's own ``simplify_phonemes`` folds away, and the ``" + "``
    word separator, all exactly as the phonetiser emits them.
    ``Alphabet.IPA`` strips the digits and converts through
    :func:`scriptconv.notation.halabi_to_ipa`.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.HALABI):
        _check_alphabet(self, alphabet, [Alphabet.IPA, Alphabet.HALABI])
        super().__init__(alphabet)
        global _halabi_backend
        if _halabi_backend is None:
            _halabi_backend = _load_halabi_backend()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["ar"])

    def phonemize_string(self, text: str, lang: str = "ar") -> str:
        self.get_lang(lang)
        arabic_to_buckwalter, process_utterance = _halabi_backend
        raw = process_utterance(arabic_to_buckwalter(text))
        if self.alphabet == Alphabet.IPA:
            cleaned = _strip_halabi_digits(raw).replace(" + ", "_+_")
            cleaned = re.sub(r"\bsil\b", "_sil_", cleaned)
            return halabi_to_ipa(cleaned)
        return raw


class IqraPhonemizer(BasePhonemizer):
    """The IqraEval shared task's flavor of the Halabi phonetiser.

    Backed by ``_vendored/iqra_phonetiser/phonetiser.py`` — a port of
    Iqra-Eval/MSA_phonetiser's own ``phonetiser/phonetise_Arabic.py``, the
    IqraEval shared task's OWN published data-prep code (confirmed, per its
    ``run_phonetiser.py``, to be what generates ``phoneme_ref`` itself), NOT
    mantoq's vendored copy of Nawar Halabi's pristine original (that copy
    backs :class:`HalabiPhonemizer`/:class:`MantoqPhonemizer` instead — see
    ``_vendored/iqra_phonetiser/LICENSE.md`` and that module's docstring for
    the full diff against both the pristine upstream and mantoq's copy, and
    why the two vendored copies must stay independent).

    Three deterministic text-level transforms are applied to the input
    *before* the phonetiser runs (see :func:`_iqra_preprocess`, each cited
    to its tajwīd/grammar name), plus the stress-digit strip every raw edge
    needs:

      1. tanwīn (nunation) dropped everywhere, not just at a pause;
      2. wāw al-jamāʿah's silent alif (``-ūا`` → ``-ū``) collapsed;
      3. utterance-initial hamzat al-waṣl on the definite article "ال"
         realized as hamza + fatḥa (``أَ``) rather than elided.

    See the introducing PR for the full methodology, the match-rate history,
    and any residual mismatch classes against ``IqraEval/Iqra_train``'s
    ``phoneme_ref`` (``scripts/benchmark_iqraeval.py``).

    ``Alphabet.HALABI`` (default) returns the cleaned native tokens
    (space-separated, digits stripped, no ``+``/``sil``, gemination as a
    literal doubled consonant letter — the ``phoneme_ref`` convention
    itself, emphatic-context uppercase vowels included: the reference keeps
    that distinction). ``Alphabet.IPA`` converts through
    :func:`scriptconv.notation.iqra_halabi_to_ipa`, which — unlike
    :func:`~scriptconv.notation.halabi_to_ipa` — keeps the emphatic-context
    vowels distinct.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.HALABI):
        _check_alphabet(self, alphabet, [Alphabet.IPA, Alphabet.HALABI])
        super().__init__(alphabet)
        global _iqra_backend
        if _iqra_backend is None:
            _iqra_backend = _load_iqra_backend()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        return cls.match_lang(target_lang, ["ar"])

    def phonemize_string(self, text: str, lang: str = "ar") -> str:
        self.get_lang(lang)
        arabic_to_buckwalter, process_utterance = _iqra_backend
        text = _iqra_preprocess(text)
        raw = process_utterance(arabic_to_buckwalter(text))
        cleaned = _strip_halabi_digits(raw)
        cleaned = cleaned.replace(" + ", " ")
        cleaned = re.sub(r"\bsil\b\s*", "", cleaned)
        cleaned = " ".join(cleaned.split())
        if self.alphabet == Alphabet.IPA:
            return iqra_halabi_to_ipa(cleaned)
        return cleaned
