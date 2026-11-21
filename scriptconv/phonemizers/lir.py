from scriptconv.phonemizers.base import BasePhonemizer, ModelUnavailableError
from scriptconv.phonemizers.enums import Alphabet


class KolokwaPhonemizer(BasePhonemizer):
    """
    Liberian English (Kolokwa) with https://huggingface.co/michsethowusu/kolokwa-g2p,
    a Forward Transformer of https://github.com/arcosoph/phonemize (MIT).
    """

    engine_distribution = "phonemize"
    REPO = "michsethowusu/kolokwa-g2p"
    REVISION = "92ed3b721a4f80f98d5b741fdd16352ca320f121"

    def __init__(self):
        try:
            from phonemize import Phonemizer
            from phonemize.preprocessing.text import LanguageTokenizer, Preprocessor, SequenceTokenizer
            from huggingface_hub import hf_hub_download
            import torch
        except ImportError as e:
            raise ImportError(
                "phonemize and huggingface_hub are required for the Kolokwa "
                "phonemizer. Install them with 'pip install scriptconv[lir]'."
            ) from e
        # torch loads the checkpoint with weights_only=True
        torch.serialization.add_safe_globals([Preprocessor, LanguageTokenizer, SequenceTokenizer])
        try:
            model = hf_hub_download(self.REPO, "best_model.pt", revision=self.REVISION)
        except Exception as e:
            raise ModelUnavailableError(
                f"{self.REPO}/best_model.pt at revision {self.REVISION} is not in the "
                f"Hugging Face cache and cannot be downloaded: {e}") from e
        self.phonemizer = Phonemizer.from_checkpoint(model)
        super().__init__(Alphabet.IPA)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """
        Validates the language code and returns the language key of the model.

        Args:
            target_lang (str): The language code to validate.

        Returns:
            str: ``"en_lr"``, the key of Liberian English in the model.

        Raises:
            ValueError: If the language code is unsupported.
        """
        cls.match_lang(target_lang, ["lir"])
        return "en_lr"

    def phonemize_string(self, text: str, lang: str = "lir") -> str:
        return self.phonemizer(text, lang=self.get_lang(lang))
