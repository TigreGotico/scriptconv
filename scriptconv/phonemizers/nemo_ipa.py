"""American English phonemizer: the IPA G2P of NVIDIA NeMo, as Magpie TTS reads it.

Magpie TTS reads English through its ``english_phoneme`` sub-tokenizer, an
``IPATokenizer`` over an ``IpaG2p``. This backend gives the symbol string
that the sub-tokenizer encodes: one character for each of the 94 symbols of
its vocabulary (the tokenizer has 96 tokens, with ``<pad>`` and ``<oov>``), so
a caller maps each character to its token id. It takes
no random draw. NeMo keeps a word as letters with a probability while it
trains, and this backend always gives the phonemes of the word.

The steps follow NeMo at commit ``fd6a877539710e2b98f28c43272ff81312f83417``
(tag v3.0.0), in these files:

- ``nemo/collections/common/tokenizers/text_to_speech/tokenizer_utils.py``:
  ``english_text_preprocessing`` and ``english_word_tokenize``;
- ``nemo/collections/tts/g2p/models/i18n_ipa.py``: ``IpaG2p``;
- ``nemo/collections/common/tokenizers/text_to_speech/tts_tokenizers.py``:
  ``IPATokenizer.encode_from_g2p``.

NeMo is Apache-2.0, Copyright (c) 2023, NVIDIA CORPORATION & AFFILIATES. See
``scriptconv/phonemizers/_thirdparty/nemo/NOTICE``. This module holds no code
of NeMo, only its logic, written again for strings.

The settings are those of the ``english_phoneme`` entry in the Magpie TTS
config: ``ignore_ambiguous_words=False`` (a word with several pronunciations
takes the first), ``use_chars=True``, ``use_stresses=True``, ``punct=True``,
``apostrophe=True`` and ``pad_with_space=False``.

The data are two files that NeMo names in that config. They are not in the
wheel. By default they come from the Hugging Face Hub, from
:data:`DATA_REPO` at :data:`DATA_REVISION`, into the shared cache, and each
must have its pinned sha256. A caller can give the path of either file.
``ipa_cmudict-0.7b_nv23.01.txt`` is the CMU Pronouncing Dictionary with IPA
pronunciations, and ``heteronyms-052722`` lists the words that NeMo leaves as
letters. The pinned dictionary is the copy in the Magpie TTS checkpoint
(sha256 ``7ea5c4c2``), not the copy in ``scripts/tts_dataset_files`` of NeMo
(sha256 ``dd0927ff``). The two have the same size and differ only in the order
of the two readings of ``A``: Magpie has ``ˈʌ`` first and NeMo has ``ˈeɪ``
first. The pin follows the checkpoint.

The output differs from NeMo in two places. NeMo stops with an ``IndexError``
on any text whose kept symbols are only spaces, as ``½ ¼ ¾``, and this backend
gives an empty string. In a span between two ``|`` marks, which NeMo keeps
unchanged, the tokens ``<pad>`` and ``<oov>`` give the id of the special token
in NeMo and nothing here.
"""
import dataclasses
import re
import unicodedata
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

from scriptconv.phonemizers.base import (
    BasePhonemizer,
    MissingLanguageError,
    PhonemizerIdentity,
    UnsupportedLanguageError,
    _check_alphabet,
)
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.g2pw import _hub_file, _sha256

__all__ = ["NemoIpaPhonemizer", "DATA_REPO", "DATA_REVISION", "DATA_FILES", "NEMO_COMMIT"]

NEMO_COMMIT = "fd6a877539710e2b98f28c43272ff81312f83417"
DATA_REPO = "Phoonnx/magpietts-multi-357m-unicode"
DATA_REVISION = "a0e169ad4a160578974af51181a126d52dab6ab6"
#: name -> (path in :data:`DATA_REPO`, sha256)
DATA_FILES = {
    "dictionary": ("assets/tokenizer/dc7d60d6b15a4651b21c9ca2932b62c6_ipa_cmudict-0.7b_nv23.01.txt",
                   "7ea5c4c2c59cc780748b24d4ab60bd689779c4ac4ea7e27c0a8c3e20f300c0fa"),
    "heteronyms": ("assets/tokenizer/61d57a4ccb064d1e8e3d9f871c571932_heteronyms-052722",
                   "b701909aedf753172eff223950f8859cd4b9b4c80199cf0a6e9ac4a307c8f8ec"),
}

_LATIN = "A-Za-z"
_WORD_CHARS = (_LATIN + "À-ÖØ-öø-ÿ"
               r"ऀ-ॣ०-ॿঀ-৿஀-௿ఀ-౿ಀ-೿઀-૿"
               r"가-힣ᄀ-ᇿ㄰-㆏")
_HAS_CHAR = re.compile(fr"[{_WORD_CHARS}\d]")
_NOT_CHAR = re.compile(fr"[^{_WORD_CHARS}\d]")
_ENTRY = re.compile(fr"[{_WORD_CHARS}']")
_ALTERNATIVE = re.compile(r"\([0-9]+\)")
# a word, a span between two bars that stays unchanged, or anything else
_ENGLISH_WORDS = re.compile(
    fr"([{_LATIN}]+(?:[{_LATIN}\-']*[{_LATIN}]+)*)|(\|[^|]*\|)|([^{_LATIN}|]+)")
_SYNOGLYPHS = str.maketrans({"’": "'", "”": '"', "“": '"'})
#: NeMo's ``DEFAULT_PUNCTUATION``, the punctuation of ``en-US``
_PUNCTUATION = frozenset(",.!?-:;/\"()[]{}")


def _preprocess(text: str) -> str:
    """*text* without combining marks and with straight quotes, in NFC, as the tokenizer and the G2P read it."""
    text = "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")
    return unicodedata.normalize("NFC", text.translate(_SYNOGLYPHS))


def _read_dictionary(path: str) -> Tuple[Dict[str, List[List[str]]], Set[str]]:
    """The pronunciations by upper-case word, and the symbols of the dictionary.

    A word with ``(2)`` and the like after it adds a pronunciation to the
    word. The symbols are the characters of each pronunciation and of each
    word without punctuation.
    """
    entries: Dict[str, List[List[str]]] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = unicodedata.normalize("NFC", line)
            if _ENTRY.match(line):
                word, pronunciation = line.strip().split(maxsplit=1)
                entries.setdefault(_ALTERNATIVE.sub("", word), []).append(list(re.sub(r"\s+", "", pronunciation)))
    pronunciations: Dict[str, List[List[str]]] = {}
    symbols: Set[str] = set()
    for word, variants in entries.items():
        word = word.upper()
        symbols.update(_NOT_CHAR.sub("", word))
        for variant in variants:
            symbols.update(variant)
        pronunciations[word] = variants
    return pronunciations, symbols


class NemoIpaPhonemizer(BasePhonemizer):
    """NVIDIA NeMo's English IPA G2P: text to the symbols of the Magpie TTS ``english_phoneme`` vocabulary.

    A word of the dictionary gives the IPA symbols of its first
    pronunciation, with the stress marks ``ˈ`` and ``ˌ``. A word of the
    heteronyms file, a word that the dictionary lacks and a digit give upper-case
    letters and digits. A character that the vocabulary lacks is dropped.
    Spaces stay, also two in a row, except at the end of the text. The
    punctuation of the vocabulary stays.

    Args:
        alphabet: must be :attr:`Alphabet.IPA`.
        dictionary: the path of a dictionary in the format of
            ``ipa_cmudict-0.7b_nv23.01.txt``. The default is the file of
            :data:`DATA_FILES`, downloaded from :data:`DATA_REPO`.
        heteronyms: the path of a file with one heteronym on each line. The
            default is the file of :data:`DATA_FILES`.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.IPA,
                 dictionary: Optional[Union[str, Path]] = None,
                 heteronyms: Optional[Union[str, Path]] = None):
        _check_alphabet(self, alphabet, [Alphabet.IPA])
        super().__init__(alphabet)
        paths: Dict[str, str] = {}
        self.sha256: Dict[str, str] = {}
        for name, given in (("dictionary", dictionary), ("heteronyms", heteronyms)):
            filename, sha256 = DATA_FILES[name]
            if given is None:
                try:
                    import huggingface_hub  # noqa: F401
                except ImportError:
                    raise ImportError(
                        "The NeMo IPA phonemizer needs huggingface_hub to download its data. Install it with "
                        "`pip install scriptconv[en-phonemizers]`, or pass the paths of the files.") from None
                paths[name] = _hub_file(DATA_REPO, "model", filename, DATA_REVISION, sha256)
                self.sha256[name] = sha256
            else:
                paths[name] = str(given)
                self.sha256[name] = _sha256(paths[name])
        self.pronunciations, symbols = _read_dictionary(paths["dictionary"])
        with open(paths["heteronyms"], encoding="utf-8") as f:
            self.heteronyms = {line.rstrip().upper() for line in f}
        self.vocabulary = symbols | _PUNCTUATION | {"'", " "}

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """*target_lang* as a standard tag, when it is American English.

        A tag with no region takes its default region, so ``en`` is ``en-GB``
        and is refused.

        Raises:
            MissingLanguageError: If no language is given.
            UnsupportedLanguageError: If the tag is not English of the US.
        """
        if target_lang in (None, "", "und"):
            raise MissingLanguageError(f"no language provided to phonemize: {target_lang!r}")
        from linguatag import closest_lang, with_default_region
        tag = with_default_region(target_lang)
        if closest_lang(tag, ["en-US"], max_distance=0) is None:
            raise UnsupportedLanguageError(
                f"unsupported language code: {target_lang}; the NeMo IPA G2P reads en-US only")
        return tag

    def phonemize_string(self, text: str, lang: str) -> str:
        self.get_lang(lang)
        symbols: List[str] = []
        for word, unchanged, other in _ENGLISH_WORDS.findall(_preprocess(text)):
            if word:
                symbols += self._read(word.lower())
            elif other:
                symbols += self._read(other)
            else:
                symbols += unchanged[1:-1].split(" ")
        return "".join(s for s in symbols if s in self.vocabulary).rstrip(" ")

    def _read(self, word: str) -> List[str]:
        """The symbols of a word, or of a run of characters between two words, as ``IpaG2p`` gives them.

        A word that is not in the dictionary is read again in parts at its
        hyphens, with a hyphen between the parts.
        """
        symbols, found = self._lookup(word)
        if not found and "-" in word:
            symbols = []
            for part in word.split("-"):
                symbols += self._lookup(part)[0] + ["-"]
            symbols.pop()
        return symbols

    def _lookup(self, word: str) -> Tuple[List[str], bool]:
        """The symbols of *word*, and whether the dictionary or a rule gave them.

        A run with no letter or digit, a heteronym and a word that the
        dictionary lacks give upper-case letters. A word in the dictionary
        gives its first pronunciation. A word with ``'s`` or ``s`` after a
        word of the dictionary gives its pronunciation and then ``s``, ``z``
        or ``ɪz``.
        """
        word = word.upper()
        if not _HAS_CHAR.search(word) or word in self.heteronyms:
            return list(word), True
        pronunciations = self.pronunciations
        if word in pronunciations:
            return pronunciations[word][0], True
        if len(word) > 2 and word.endswith("'S") and word[:-2] in pronunciations:
            stem = word[:-2]
            ending = ["s"] if stem[-1] == "T" else ["ɪ", "z"] if stem[-1] == "S" else ["z"]
            return pronunciations[stem][0] + ending, True
        if len(word) > 1 and word.endswith("S") and word[:-1] in pronunciations:
            stem = word[:-1]
            return pronunciations[stem][0] + ["s" if stem[-1] == "T" else "z"], True
        return list(word), False

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the hash of the code on the
        path of this backend, as
        :func:`~scriptconv.phonemizers._revision.code_revision` gives it, and
        of the sha256 of the dictionary and of the heteronyms file."""
        from scriptconv.phonemizers._revision import code_revision
        identity = super().identity(lang)
        return dataclasses.replace(identity, revision=code_revision(self, identity.lang, self.sha256))
