"""American English phonemizer: Leokani G2P.

Leokani G2P by Milliwatt Labs (milliwattlabs.com) reads English text into the
phoneme codes of Kokoro and misaki, with stress marks. It looks each word up
in its lexicon, reads digits with its number reader, and guesses the other
words with a letter-to-sound model. A context model then picks how each word
is said in its clause. Its own text rules first write numbers, money, dates,
times and units as words. Its reference readings are American English.

Its code (MIT) is vendored under
:mod:`scriptconv.phonemizers._thirdparty.leokani`. Its model files (CC BY 4.0)
come from the Hugging Face Hub, from :data:`MODEL_REPO` at
:data:`MODEL_REVISION`, into the shared Hugging Face cache. That repository is
a byte-identical copy of milliwattlabs/leokani-g2p at revision
a819acc86471a04a01ba3d3f30f3765e4675c7ca. Each file must have its pinned
sha256. Offline, with no cached copy that passes the check, the backend raises
:class:`~scriptconv.phonemizers.base.ModelUnavailableError`.
"""
import dataclasses
from typing import Dict

try:
    import huggingface_hub  # noqa: F401
    import onnxruntime  # noqa: F401

    from scriptconv.phonemizers._thirdparty.leokani.leokani_g2p import LeokaniG2P
except ImportError:
    raise ImportError(
        "Leokani G2P needs numpy, onnxruntime and huggingface_hub — install with "
        "`pip install scriptconv[en-phonemizers]`") from None

from scriptconv.phonemizers.base import (
    BasePhonemizer,
    MissingLanguageError,
    PhonemizerIdentity,
    UnsupportedLanguageError,
    _check_alphabet,
)
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.g2pw import _hub_file

__all__ = ["LeokaniPhonemizer", "MODEL_REPO", "MODEL_REVISION", "MODEL_FILES"]

MODEL_REPO = "TigreGotico/leokani-g2p"
MODEL_REVISION = "60f16f36e79bc37525b0ce6a7b22bd50c54c331f"
#: variant -> {path in :data:`MODEL_REPO`: sha256}. ``micro`` is upstream's default.
MODEL_FILES = {
    "micro": {
        "leokani-g2p.data": "b25d3baf82efc5da668b47bf34a86e7900378b2236d56bcf75cfd4a167d61a1b",
        "leokani-g2p-words.data": "fa88a96b7e42c61b8e7b9acaf9787e8537d3d1e8dd4e06764e05e75537fc2aa2",
        "oov-encoder.onnx": "4a91d053c5cba5b910bc8aa4c1301e2db4dd33f47b9e3841df9e4596efb7ef3a",
        "oov-decoder.onnx": "fe951d01dc9f2b8e1e3a6bba224ba74ea256713029c8512a02c4192ca503619e",
        "context.onnx": "b525b8e290004d33f5996c4954bcf289654806133b32289b7842c49da5ac1d20",
    },
    "mini": {
        "mini/leokani-g2p.data": "d27775335b05bccb67bfc8fd905e90acaa985a25deffa969d5361762d6f57536",
        "mini/leokani-g2p-words.data": "2c62d8d9758954af58e799c2845d7906a7cbeb24e95e702b39f199c86b8c1ba6",
        "mini/oov-encoder.onnx": "cb3d78b31912a95a871fb19c9371e3350fb7f2a7ee13038a3c990ddc669e9172",
        "mini/oov-decoder.onnx": "11a08d5e31c2abb4335fd3bc2531a277b7652afe37b6ecb61f579aca68778565",
        "mini/context.onnx": "b525b8e290004d33f5996c4954bcf289654806133b32289b7842c49da5ac1d20",
    },
}


class LeokaniPhonemizer(BasePhonemizer):
    """Leokani G2P: American English text to Kokoro and misaki phoneme codes.

    The codes are those of the ``misaki_en`` backend: IPA, with ``A``, ``I``,
    ``O``, ``W`` and ``Y`` for the diphthongs eɪ, aɪ, oʊ, aʊ and ɔɪ, and
    ``ᵊ`` and ``ᵻ`` for reduced vowels. :meth:`phonemize_string` returns
    upstream's ``LeokaniG2P.phonemize`` unchanged, with the punctuation that
    the text holds.

    Args:
        alphabet: must be :attr:`Alphabet.IPA`.
        variant: ``"micro"`` (the default) or ``"mini"``, which is larger and
            reads names and rare words better.
    """

    def __init__(self, alphabet: Alphabet = Alphabet.IPA, variant: str = "micro"):
        _check_alphabet(self, alphabet, [Alphabet.IPA])
        if variant not in MODEL_FILES:
            raise ValueError(f"unknown Leokani G2P variant {variant!r}; use one of {', '.join(MODEL_FILES)}")
        super().__init__(alphabet)
        self.variant = variant
        for name, sha256 in MODEL_FILES[variant].items():
            path = _hub_file(MODEL_REPO, "model", name, MODEL_REVISION, sha256)
        # the cached path ends in the repository path; before it is the snapshot of the revision
        self.engine = LeokaniG2P(path.removesuffix(name), variant=variant)

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
                f"unsupported language code: {target_lang}; Leokani G2P reads en-US only")
        return tag

    def phonemize_string(self, text: str, lang: str) -> str:
        self.get_lang(lang)
        return self.engine.phonemize(text)

    def _revision_arguments(self) -> Dict[str, object]:
        return {"variant": self.variant}

    def identity(self, lang: str) -> PhonemizerIdentity:
        """The base identity, with ``revision`` the hash of the code on the
        path of this backend, as
        :func:`~scriptconv.phonemizers._revision.code_revision` gives it. That
        code holds the vendored engine and the pinned model revision and
        sha256 of each model file."""
        from scriptconv.phonemizers._revision import code_revision
        identity = super().identity(lang)
        return dataclasses.replace(identity, revision=code_revision(self, identity.lang, {}))
