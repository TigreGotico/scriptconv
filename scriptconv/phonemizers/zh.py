"""Chinese phonemizers: Jieba segmentation, and pinyin backends with IPA output.

The erhua suffix follows Wikipedia, "Standard Chinese phonology", revision
1384691172. The section "Rhotic coda" says: "Standard Chinese features
syllables that end with a rhotic coda /ɚ/." Of its second case it says: "In
syllables in which the rhotic coda is added as a suffix to another morpheme.
This suffix is represented by the character 儿 […] and in pinyin as r. The
suffix combines with the final sound of the syllable, and regular but complex
sound changes occur as a result (described in detail under erhua)." The
section "Syllables" gives the coda as "one of [n, ŋ, ɚ̯, i̯, u̯]".

So when g2pM reads 儿 after a syllable as ``r5``, that token is the coda ɚ̯
of the syllable before it, and not a syllable of its own. The coda goes before
the tone mark, where the output writes the other vocalic codas (爱 ai̯↘, 后
xou̯↘), and after a nasal coda, which follows the tone mark. The sound changes
to the rest of the final are not applied. A Latin ``r`` that a backend passes
through is not pinyin and gives no IPA. A backend that writes the suffix as
``er`` gives the same token as the independent morpheme 儿 ér, so that suffix
reads as a full syllable.

g2pM joins its tokens with ``|`` and splits them on ``|``, unless
``char_split`` is set. So a ``|`` in the text gives no token, and the alignment
of tokens to characters steps over it. A 儿 after a ``|`` does not follow a
syllable, so it gets no coda. g2pM also writes a reading of one letter with no
``|`` around it, so that reading joins the tokens next to it, and the token of
each character is not known. Its dictionary reads A, P, Q and T as one letter,
and with ``tone=False`` g2pM reads a, e, o, m and the suffix r as one letter.
So when the text holds A, P, Q or T, or when ``tone`` is off, no suffix gets
the coda: it logs a warning, or raises in strict mode.
"""
import abc
import logging
import re
import unicodedata
from typing import List


from scriptconv.phonemizers.base import BasePhonemizer, UnreadTextError, _check_alphabet
from scriptconv.phonemizers._thirdparty.zh_num import num2str
from scriptconv.phonemizers.enums import Alphabet

LOG = logging.getLogger(__name__)

# Pinyin writes ü with its dots only after n and l, and nüe and lüe keep them
# too (Wikipedia, "Pinyin", revision 1384755350, section "The ⟨ü⟩ sound").
# g2pc and g2pM write ü as "u:", as CC-CEDICT does, and xpinyin writes "nue".
# pinyin_to_ipa reads "ü" and "v", and rejects "u:" and "nue".
_NUE_LUE = re.compile(r"^([nl])u(?=[eēéěè])")

# The erhua suffix as g2pM spells it, with or without the tone number
_ERHUA_SUFFIX = re.compile(r"r[1-5]?")
# The tone mark at the end of a syllable in the IPA output
_FINAL_TONE = re.compile(r"[˥˦˧˨˩→↗↓↘]*$")


class _ErhuaSuffix(str):
    """A pinyin token ``r`` that g2pM read from the character 儿."""


def _standard_pinyin(syllable: str) -> str:
    """*syllable* with ü spelled as the pinyin standard spells it."""
    return _NUE_LUE.sub(r"\1ü", syllable.replace("u:", "ü"))



class JiebaPhonemizer(BasePhonemizer):
    """
    A non-phonemizing class that simply uses Jieba to segment Chinese text
    into words with spaces for token separation.
    """

    engine_distribution = "jieba"
    def __init__(self):
        super().__init__(Alphabet.HANZI)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Validates and returns the closest supported language code.

        Args:
            target_lang (str): The language code to validate.

        Returns:
            str: The validated language code.

        Raises:
            ValueError: If the language code is unsupported.
        """
        # this check is here only to throw an exception if invalid language is provided
        return cls.match_lang(target_lang, ["zh"])

    def phonemize_string(self, text: str, lang: str = "zh") -> str:
        """
        Segments the input Chinese text using Jieba.

        Args:
            text (str): The input sentence.
            lang (str): Language code (must be "zh").

        Returns:
            str: Tokenized text with words separated by spaces.
        """
        try:
            import jieba
        except ImportError as e:
            raise ImportError(
                "jieba is required for the Jieba phonemizer. "
                "Install it with 'pip install jieba' "
                "(or 'pip install scriptconv[zh-phonemizers]')."
            ) from e
        lang = self.get_lang(lang)
        seg_list = jieba.cut(text, cut_all=False)
        # NFKC folds full-width digits (e.g. "３") to ASCII so num2str's
        # DIGITS table (keyed by ASCII "0"-"9") never raises KeyError on them
        seg_list = [num2str(unicodedata.normalize("NFKC", w)) if w.isdigit() else w for w in seg_list]
        return " ".join(seg_list)


class BaseChinesePinyinPhonemizer(BasePhonemizer):
    """
    Base class for Chinese phonemizers using different pinyin G2P libraries.
    Supports optional IPA conversion and segmentation via Jieba.
    """

    def __init__(self, alphabet=Alphabet.PINYIN, jieba: bool = True, retone=True):
        """
        Initializes the phonemizer.

        Args:
            ipa (bool): Whether to convert pinyin to IPA.
            jieba (bool): Whether to segment text using Jieba before phonemization.
        """
        _check_alphabet(self, alphabet, [Alphabet.PINYIN, Alphabet.IPA])
        super().__init__(alphabet)
        self.jieba = jieba
        self.retone = retone
        try:
            from pinyin_to_ipa import pinyin_to_ipa
        except ImportError:
            raise ImportError(
                "pinyin->IPA conversion needs pinyin_to_ipa — install with "
                "`pip install scriptconv[zh-phonemizers]`"
            ) from None
        self.pinyin_to_ipa = pinyin_to_ipa

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Validates and returns the closest supported language code.

        Args:
            target_lang (str): The language code to validate.

        Returns:
            str: The validated language code.

        Raises:
            ValueError: If the language code is unsupported.
        """
        # this check is here only to throw an exception if invalid language is provided
        return cls.match_lang(target_lang, ["zh"])

    @staticmethod
    def _retone(p):
        p = p.replace('˧˩˧', '↓')  # third tone
        p = p.replace('˧˥', '↗')  # second tone
        p = p.replace('˥˩', '↘')  # fourth tone
        p = p.replace('˥', '→')  # first tone
        p = p.replace(chr(635) + chr(809), 'ɨ').replace(chr(633) + chr(809), 'ɨ')
        # U+0329 (combining vertical line below, syllabic diacritic) is only
        # ever expected attached to ɻ/ɹ (U+027B/U+0279) above, which the two
        # replacements just consumed; any leftover means pinyin_to_ipa
        # emitted an unanticipated syllabic marking. Rather than crashing in
        # production, leave it in place — it's still valid IPA, just not
        # collapsed to the ɨ shorthand.
        return p

    def to_ipa(self, phones: List[str]) -> List[str]:
        """
        Converts a list of pinyin syllables to IPA.

        A token with no letters or digits, such as punctuation, is kept as it
        is. An erhua suffix that the backend read from 儿 gives the coda ɚ̯ of
        the syllable before it. A syllable that is not pinyin gives no IPA: it
        logs a warning, or raises :class:`UnreadTextError` when :attr:`strict`
        is set.

        Args:
            phones (List[str]): List of pinyin syllables or phrases.

        Returns:
            List[str]: Corresponding IPA.
        """
        ipa_phones: List[str] = []
        for p in phones:
            if p == " ":
                ipa_phones.append(" ")
                continue
            if isinstance(p, _ErhuaSuffix):
                host = ipa_phones[-1]
                tone = _FINAL_TONE.search(host).start()
                ipa_phones[-1] = host[:tone] + "ɚ̯" + host[tone:]
                ipa_phones.append("")
                continue
            pho_str = ""
            for sp in p.split():  # G2P might return phrases with multiple syllables
                if not any(c.isalnum() for c in sp):
                    pho_str += sp
                    continue
                try:
                    readings = self.pinyin_to_ipa(_standard_pinyin(sp))
                except ValueError:
                    message = f"no IPA for {sp!r}, which is not pinyin"
                    if self.strict:
                        raise UnreadTextError(message, (sp,)) from None
                    LOG.warning(message)
                    continue
                # pinyin_to_ipa gives the Taiwan reading [ɚ] of er first, and
                # the mainland reading [aɚ̯] second (Wikipedia, "Standard
                # Chinese phonology", revision 1384691172, section "Rhotic
                # coda"). The language code holds no region here, so every
                # er takes the mainland reading.
                reading = next((r for r in readings if r[0].startswith("aɚ̯")), readings[0])
                pho = "".join(reading)
                if self.retone:
                    pho = self._retone(pho)
                pho_str += pho
            ipa_phones.append(pho_str)
        return ipa_phones

    @staticmethod
    def remove_punctuation(text: str) -> str:
        """*text* without punctuation, as :meth:`BasePhonemizer.remove_punctuation` writes it.

        A full-width mark, such as ``？`` or ``、``, stands between two words
        with no space, so it becomes a space: Jieba then cuts the words there,
        as it does when it reads the mark.
        """
        return BasePhonemizer.remove_punctuation("".join(
            " " if unicodedata.category(char).startswith("P")
            and unicodedata.east_asian_width(char) in ("W", "F", "H") else char
            for char in text))

    def phonemize_to_list(self, text: str, lang: str) -> List[str]:
        phones: List[str] = []
        lang = self.get_lang(lang)
        if self.jieba:
            import jieba
            for chunk in jieba.cut(text, cut_all=False):
                if chunk.isspace():
                    continue  # each word already ends in a space
                if chunk.isdigit():
                    # NFKC folds full-width digits (e.g. "３") to ASCII so
                    # num2str's DIGITS table never raises KeyError on them
                    chunk = num2str(unicodedata.normalize("NFKC", chunk))
                phones += self.get_pinyin(chunk)
                phones += [" "]  # keep jieba whitespace
        else:
            phones = self.get_pinyin(text)
        if self.alphabet == Alphabet.IPA:
            phones = self.to_ipa(phones)
        return phones

    def phonemize_string(self, text: str, lang: str = "zh") -> str:
        """
        Converts input text to a space-separated phoneme string.

        Args:
            text (str): The input sentence.
            lang (str): Language code (must be "zh").

        Returns:
            str: Space-separated phoneme string.
        """
        phones: List[str] = self.phonemize_to_list(text, lang)
        return "".join(phones)

    @abc.abstractmethod
    def get_pinyin(self, text: str) -> List[str]:
        """
        Abstract method to be implemented by subclasses for converting text to pinyin.

        Args:
            text (str): Input Chinese text.

        Returns:
            List[str]: List of pinyin tokens.
        """
        return NotImplemented


class G2pCPhonemizer(BaseChinesePinyinPhonemizer):
    """
    Phonemizer using g2pc (CRF-based Grapheme-to-Phoneme converter).
    https://github.com/Kyubyong/g2pC
    """

    engine_distribution = "g2pc"

    def __init__(self, alphabet=Alphabet.PINYIN, jieba: bool = True):
        try:
            from g2pc import G2pC
        except ImportError:
            raise ImportError(
                "g2pc phonemization needs g2pc, and no scriptconv extra can "
                "install it. g2pc needs pkuseg, which has wheels for CPython "
                "3.5 to 3.8 only. The pkuseg sdist imports numpy in its "
                "setup.py and does not declare numpy as a build dependency, "
                "so an isolated build fails. Run 'pip install numpy cython "
                "setuptools', then 'pip install --no-build-isolation g2pc'."
            ) from None
        self.g2p = G2pC()
        super().__init__(alphabet, jieba)

    def get_pinyin(self, text: str) -> List[str]:
        """
        Returns a list of pinyin syllables from g2pc.

        Args:
            text (str): Input Chinese text.

        Returns:
            List[str]: Pinyin tokens.
        """
        return [a[3] for a in self.g2p(text)]


class G2pMPhonemizer(BaseChinesePinyinPhonemizer):
    """
    Phonemizer using g2pM - A Neural Grapheme-to-Phoneme Conversion Package for Mandarin Chinese
    https://github.com/kakaobrain/g2pm
    """

    engine_distribution = "g2pM"

    def __init__(self, alphabet=Alphabet.PINYIN, tone: bool = True, char_split: bool = False, jieba: bool = True):
        try:
            from g2pM import G2pM
        except ImportError:
            raise ImportError(
                "g2pM phonemization needs g2pM — install with "
                "`pip install scriptconv[zh-phonemizers]`"
            ) from None
        self.g2p = G2pM()
        self._one_letter = frozenset(char for char, readings in self.g2p.cedict.items()
                                     if any(len(reading) == 1 for reading in readings))
        self.tone = tone
        self.char_split = char_split
        super().__init__(alphabet, jieba)

    def get_pinyin(self, text: str) -> List[str]:
        """
        Returns a list of pinyin tokens from g2pM.

        Args:
            text (str): Input Chinese text.

        Returns:
            List[str]: Pinyin tokens.
        """
        tokens = self.g2p(text, tone=self.tone, char_split=self.char_split)
        # g2pM writes a reading of one letter with no "|" around it, so it joins
        # that reading to the tokens next to it. Readings of one letter come
        # from the characters in _one_letter, and from many more without tones.
        if not self.tone or not self._one_letter.isdisjoint(text):
            return tokens
        # Each other reading is one token. g2pM joins the characters that it
        # does not read and that follow each other into one token, so a token
        # that does not start the rest of the text was read from the character
        # at pos. Unless char_split is set, g2pM joins its tokens with "|" and
        # splits them on "|": a "|" in the text gives no token, and it gives an
        # empty token where it follows a reading.
        pos, after_syllable = 0, False
        for i, token in enumerate(tokens):
            while not self.char_split and text.startswith("|", pos):
                pos += 1
                after_syllable = False
            if text.startswith(token, pos):
                pos += len(token)
                after_syllable = False
                continue
            if after_syllable and text[pos] == "儿" and _ERHUA_SUFFIX.fullmatch(token):
                tokens[i] = _ErhuaSuffix(token)
            pos += 1
            after_syllable = True
        return tokens


class XpinyinPhonemizer(BaseChinesePinyinPhonemizer):
    """
    Phonemizer using xpinyin (basic pinyin generator with optional tone marks).
    """

    engine_distribution = "xpinyin"

    def __init__(self, alphabet=Alphabet.PINYIN, tone_marks: str = "numbers", jieba: bool = True):
        try:
            from xpinyin import Pinyin
        except ImportError:
            raise ImportError(
                "xpinyin phonemization needs xpinyin — install with "
                "`pip install scriptconv[zh-phonemizers]`"
            ) from None
        self.g2p = Pinyin()
        self.tone_marks = tone_marks
        super().__init__(alphabet, jieba)

    def get_pinyin(self, text: str) -> List[str]:
        """
        Returns a list of pinyin tokens from xpinyin.

        Args:
            text (str): Input Chinese text.

        Returns:
            List[str]: Pinyin tokens.
        """
        return self.g2p.get_pinyin(text, tone_marks=self.tone_marks).split("-")


class PypinyinPhonemizer(BaseChinesePinyinPhonemizer):
    """
    Phonemizer using pypinyin (comprehensive and accurate pinyin library).
    """

    engine_distribution = "pypinyin"

    def __init__(self, alphabet=Alphabet.PINYIN, jieba: bool = True):
        try:
            from pypinyin import pinyin
        except ImportError:
            raise ImportError(
                "pypinyin phonemization needs pypinyin — install with "
                "`pip install scriptconv[zh]`"
            ) from None
        self.g2p = pinyin
        super().__init__(alphabet, jieba)

    def get_pinyin(self, text: str) -> List[str]:
        """
        Returns a list of pinyin tokens from pypinyin.

        Args:
            text (str): Input Chinese text.

        Returns:
            List[str]: Pinyin tokens.
        """
        return [p[0] for p in self.g2p(text)]
