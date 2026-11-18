from scriptconv.notation import _ARPA_TO_IPA as arpa_to_ipa_lookup
from scriptconv.phonemizers.base import BasePhonemizer
from scriptconv.phonemizers.enums import Alphabet


class DeepPhonemizer(BasePhonemizer):
    """Text to IPA or ARPA with DeepPhonemizer (https://github.com/spring-media/DeepPhonemizer).

    A model name of :attr:`MODELS` downloads into ``~/.local/share/deepphonemizer``
    on first use. A model whose name holds ``ipa`` emits IPA, any other ARPA.
    """

    engine_distribution = "deep-phonemizer"
    MODELS = {
        "latin_ipa_forward.pt": "https://public-asai-dl-models.s3.eu-central-1.amazonaws.com/DeepPhonemizer/latin_ipa_forward.pt",
        "en_us_cmudict_ipa_forward.pt": "https://public-asai-dl-models.s3.eu-central-1.amazonaws.com/DeepPhonemizer/en_us_cmudict_ipa_forward.pt",
        "en_us_cmudict_forward.pt": "https://public-asai-dl-models.s3.eu-central-1.amazonaws.com/DeepPhonemizer/en_us_cmudict_forward.pt"
    }

    def __init__(self, model="latin_ipa_forward.pt"):
        import os

        try:
            import dp
            from dp.phonemizer import Phonemizer
            import torch
        except ImportError as e:
            raise ImportError(
                "deep-phonemizer and torch are required for the DeepPhonemizer "
                "phonemizer. Install them with 'pip install deep-phonemizer torch' "
                "(or 'pip install scriptconv[en-phonemizers]')."
            ) from e
        # torch.load reads these classes of a checkpoint only when they are allowed
        torch.serialization.add_safe_globals([dp.preprocessing.text.Preprocessor])
        torch.serialization.add_safe_globals([dp.preprocessing.text.LanguageTokenizer])
        torch.serialization.add_safe_globals([dp.preprocessing.text.SequenceTokenizer])

        if "ipa" in model:
            super().__init__(Alphabet.IPA)
        else:
            super().__init__(Alphabet.ARPA)

        if not os.path.isfile(model):
            if model in self.MODELS:
                url = self.MODELS[model]
                cache_dir = os.path.expanduser("~/.local/share/deepphonemizer")
                os.makedirs(cache_dir, exist_ok=True)
                model_path = os.path.join(cache_dir, model)
                if not os.path.isfile(model_path):
                    import requests
                    print(f"Downloading {model} from {url}...")
                    with requests.get(url, stream=True) as r:
                        r.raise_for_status()
                        with open(model_path, 'wb') as f:
                            for chunk in r.iter_content(chunk_size=8192):
                                f.write(chunk)
                    print(f"Saved model to {model_path}")
                model = model_path
            else:
                raise ValueError("invalid model")

        self.phonemizer = Phonemizer.from_checkpoint(model)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The closest of ``de`` and ``en_us`` to *target_lang*.

        Raises:
            UnsupportedLanguageError: If none is close enough.
        """
        return cls.match_lang(target_lang, ['de', 'en_us'])

    def phonemize_string(self, text: str, lang: str) -> str:
        """The phonemes of *text* from the checkpoint's model for *lang*."""
        lang = self.get_lang(lang)
        return self.phonemizer(text, lang)


class OpenPhonemizer(BasePhonemizer):
    """English text to IPA with OpenPhonemizer (https://github.com/NeuralVox/OpenPhonemizer)."""

    engine_distribution = "openphonemizer"

    def __init__(self):
        try:
            from openphonemizer import OpenPhonemizer
            import torch
            import dp
        except ImportError as e:
            raise ImportError(
                "openphonemizer and torch are required for the OpenPhonemizer "
                "phonemizer. Install them with 'pip install openphonemizer torch' "
                "(or 'pip install scriptconv[en-phonemizers]')."
            ) from e
        torch.serialization.add_safe_globals([dp.preprocessing.text.Preprocessor])
        torch.serialization.add_safe_globals([dp.preprocessing.text.LanguageTokenizer])
        torch.serialization.add_safe_globals([dp.preprocessing.text.SequenceTokenizer])

        self.phonemizer = OpenPhonemizer()
        super().__init__(Alphabet.IPA)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The closest of ``en`` to *target_lang*.

        Raises:
            UnsupportedLanguageError: If none is close enough.
        """
        return cls.match_lang(target_lang, ["en"])

    def phonemize_string(self, text: str, lang: str) -> str:
        """The IPA of *text*, after a check that *lang* is English."""
        self.get_lang(lang)
        return self.phonemizer(text)


class G2PEnPhonemizer(BasePhonemizer):
    """English text to IPA or ARPA with g2p_en (https://github.com/Kyubyong/g2p)."""

    engine_distribution = "g2p_en"

    def __init__(self, alphabet=Alphabet.IPA):
        assert alphabet in [Alphabet.IPA, Alphabet.ARPA]
        try:
            import nltk
            nltk.download('averaged_perceptron_tagger_eng')
            nltk.download('cmudict')
            from g2p_en import G2p
        except ImportError as e:
            raise ImportError(
                "g2p_en is required for the G2PEn phonemizer. "
                "Install it with 'pip install g2p_en' "
                "(or 'pip install scriptconv[en-phonemizers]')."
            ) from e
        self.g2p = G2p()
        super().__init__(alphabet)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The closest of ``en`` to *target_lang*.

        Raises:
            UnsupportedLanguageError: If none is close enough.
        """
        return cls.match_lang(target_lang, ["en"])

    def phonemize_string(self, text: str, lang: str) -> str:
        """The ARPA symbols of *text* from g2p_en, mapped to IPA unless the alphabet is ARPA."""
        self.get_lang(lang)
        if self.alphabet == Alphabet.ARPA:
            return self.g2p(text)
        return "".join([arpa_to_ipa_lookup.get(pho, pho) for pho in self.g2p(text)])
