"""Phonemizers that read many languages: ByT5, Charsiu, gruut, goruut, epitran and Phonetisaurus."""

import json
import os
import shutil
import subprocess
import threading
import weakref
from typing import List, Dict, Optional, Sequence, TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np

from scriptconv.diacritics import _diacritizer_family, strip_diacritics
from scriptconv.phonemizers._moved import deprecated_getattr
from scriptconv.phonemizers.enums import Alphabet
from scriptconv.phonemizers.base import BasePhonemizer, UnsupportedLanguageError, _check_alphabet

ProviderSpec = str


def make_session(model_path, providers=None, use_cuda=False):
    """An ONNX Runtime session for *model_path* on *providers*, by default the CPU, or CUDA then CPU with *use_cuda*."""
    import onnxruntime
    if providers is None:
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"] if use_cuda \
            else ["CPUExecutionProvider"]
    return onnxruntime.InferenceSession(model_path, providers=list(providers))


# Hong Kong and Macau Cantonese. A bare "yue" means mainland Cantonese in
# Simplified script, so these tags are far from it by language distance. The
# Cantonese resources of Charsiu, Goruut and Transphone carry no region and are
# written in Traditional script, so these tags resolve to them directly.
_HK_CANTONESE = frozenset({
    "yue-hk", "yue-mo", "yue-hant", "yue-hant-hk", "yue-hant-mo",
    "zh-hk", "zh-mo", "zh-hant-hk", "zh-hant-mo",
})


def _is_hk_cantonese(lang: str) -> bool:
    """Whether *lang* names Hong Kong or Macau Cantonese."""
    return lang.lower().replace("_", "-") in _HK_CANTONESE


class ByT5Phonemizer(BasePhonemizer):
    """Text to IPA with a ByT5 ONNX model.

    scriptconv never downloads a model. :attr:`MODEL2URL` and
    :attr:`TOKENIZER_CONFIG_URL` name the published files; the caller passes
    local paths.
    """
    MODEL2URL = {
        "OpenVoiceOS/g2p-mbyt5-12l-ipa-childes-espeak-onnx": "https://huggingface.co/OpenVoiceOS/g2p-mbyt5-12l-ipa-childes-espeak-onnx/resolve/main/fdemelo_g2p-mbyt5-12l-ipa-childes-espeak.onnx",
    }
    TOKENIZER_CONFIG_URL = "https://huggingface.co/OpenVoiceOS/g2p-multilingual-byt5-tiny-8l-ipa-childes-onnx/resolve/main/tokenizer_config.json"

    BYT5_LANGS =['ca-ES', 'cy-GB', 'da-DK', 'de-DE', 'en-GB', 'en-US', 'es-ES', 'et-EE', 'eu-ES', 'fa-IR', 'fr-FR',
                 'ga-IE', 'hr-HR', 'hu-HU', 'id-ID', 'is-IS', 'it-IT', 'ja-JP', 'ko-KR', 'nb-NO', 'nl-NL', 'pl-PL',
                 'pt-BR', 'pt-PT', 'qu-PE', 'ro-RO', 'sr-RS', 'sv-SE', 'tr-TR', 'yue-CN', 'zh-CN']

    def __init__(self, model: Optional[str] = None, tokenizer_config: Optional[str] = None,
                 providers: Optional[Sequence[ProviderSpec]] = None,
                 use_cuda=bool(os.environ.get("CUDA", False))):
        """
        Args:
            model: Path to the ONNX model file.
            tokenizer_config: Path to the tokenizer configuration JSON file.
            providers: Ordered ONNX Runtime execution providers.
            use_cuda: Without *providers*, run on CUDA, then the CPU.

        Raises:
            ValueError: If *model* or *tokenizer_config* is not a local file.
        """
        super().__init__(Alphabet.IPA)
        if not model or not os.path.isfile(model):
            raise ValueError(
                "ByT5 phonemization needs a local ONNX model file: pass "
                "model=<path> (scriptconv never downloads — see MODEL2URL "
                "for the published model, or let your TTS stack resolve it)")
        if not tokenizer_config or not os.path.isfile(tokenizer_config):
            raise ValueError(
                "ByT5 phonemization needs a local tokenizer_config.json: "
                "pass tokenizer_config=<path> (see TOKENIZER_CONFIG_URL)")
        self.onnx_model_path = model
        self.tokenizer_config = tokenizer_config

        self.session = make_session(self.onnx_model_path, providers=providers, use_cuda=use_cuda)
        with open(self.tokenizer_config, "r") as f:
            self.tokens: Dict[str, int] = json.load(f).get("added_tokens_decoder", {})

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The closest tag of :attr:`BYT5_LANGS` to *target_lang*.

        Raises:
            UnsupportedLanguageError: If no tag is close enough.
        """
        return cls.match_lang(target_lang, cls.BYT5_LANGS)

    def _decode_phones(self, preds: List[int]) -> str:
        """The UTF-8 text of the predicted token ids, without the added tokens."""
        phone_bytes = [bytes([token - 3]) for token in preds if str(token) not in self.tokens]
        return b''.join(phone_bytes).decode("utf-8", errors="ignore")

    @classmethod
    def _encode_text(cls, text: str, lang: str) -> "np.ndarray":
        """The model input ids of ``<lang>: text``.

        The ByT5 tokenizer maps byte ``b`` to id ``b + 3``, after the ids of
        ``<pad>``, ``</s>`` and ``<unk>``.
        """
        import numpy as np
        encoded_bytes = f"<{cls.get_lang(lang)}>: {text}".encode("utf-8")
        return np.array([list(byte + 3 for byte in encoded_bytes)], dtype=np.int64)

    def _infer_onnx(self, text: str, lang: str) -> str:
        """The phonemes of *text* by greedy decoding, at most 512 tokens, or ``""`` for blank text."""
        import numpy as np
        if not text.strip():
            return ""
        onnx_output_names = [out.name for out in self.session.get_outputs()]
        input_ids = self._encode_text(text, lang)
        attention_mask = np.ones_like(input_ids, dtype=np.int64)
        decoder_input_ids = np.array([[0]], dtype=np.int64)  # <pad> starts the decoder
        eos_token_id = 1  # </s>
        generated_ids: List[int] = []
        for _ in range(512):
            logits = self.session.run(onnx_output_names, {"input_ids": input_ids,
                                                          "attention_mask": attention_mask,
                                                          "decoder_input_ids": decoder_input_ids})[0]
            next_token_id: int = np.argmax(logits[0, -1, :]).item()
            generated_ids.append(next_token_id)
            if next_token_id == eos_token_id:
                break
            decoder_input_ids = np.concatenate(
                (decoder_input_ids, np.array([[next_token_id]], dtype=np.int64)), axis=1)
        return self._decode_phones(generated_ids)

    def phonemize_string(self, text: str, lang: str) -> str:
        return self._infer_onnx(text, lang)


class CharsiuPhonemizer(ByT5Phonemizer):
    """Text to IPA with a CharsiuG2P ByT5 ONNX model, one word at a time."""
    MODEL2URL = {
        "Jarbas/charsiu_g2p_multilingual_byT5_tiny_16_layers_100_onnx": "https://huggingface.co/Jarbas/charsiu_g2p_multilingual_byT5_tiny_16_layers_100_onnx/resolve/main/charsiu_g2p_multilingual_byT5_tiny_16_layers_100.onnx"
    }
    BYT5_LANGS = ['ady', 'afr', 'sqi', 'amh', 'ara', 'arg', 'arm-e', 'arm-w', 'aze', 'bak', 'eus', 'bel', 'ben', 'bos',
                  'bul', 'bur', 'cat', 'yue', 'zho-t', 'zho-s', 'min', 'cze', 'dan', 'dut', 'eng-uk', 'eng-us', 'epo',
                  'est', 'fin', 'fra', 'fra-qu', 'gla', 'geo', 'ger', 'gre', 'grc', 'grn', 'guj', 'hin', 'hun', 'ido',
                  'ind', 'ina', 'ita', 'jam', 'jpn', 'kaz', 'khm', 'kor', 'kur', 'lat-clas', 'lat-eccl', 'lit', 'ltz',
                  'mac', 'mlt', 'tts', 'nob', 'ori', 'pap', 'fas', 'pol', 'por-po', 'por-bz', 'ron', 'rus', 'san',
                  'srp', 'hbs-latn', 'hbs-cyrl', 'snd', 'slo', 'slv', 'spa', 'spa-latin', 'spa-me', 'swa', 'swe', 'tgl',
                  'tam', 'tat', 'tha', 'tur', 'tuk', 'ukr', 'vie-n', 'vie-c', 'vie-s', 'wel-nw', 'wel-sw', 'ice', 'ang',
                  'gle', 'enm', 'syc', 'glg', 'sme', 'egy']
    # BCP-47 tags for the labels whose code does not name the script of their
    # CharsiuG2P data. dicts/srp.tsv is Serbian in Cyrillic, eSpeak NG output
    # over a word list (the CharsiuG2P README says some word lists come from
    # the Leipzig Corpora Collection). Its tag ties with hbs-cyrl, the WikiPron
    # Serbo-Croatian list, so a Serbian request in Cyrillic picks srp only
    # because srp comes first in BYT5_LANGS. dicts/zho-s.tsv and dicts/zho-t.tsv
    # are ipa-dict Mandarin in Simplified and Traditional script. Their cmn
    # tags keep Cantonese, Hokkien and the other Chinese languages away from
    # them. dicts/kur.tsv is the AsoSoft Central Kurdish data, "Central Kurdish
    # words in Standard Arabic script", which a Kurmanji request in Latin
    # script must not reach. dicts/fra-qu.tsv is ipa-dict fr_QC, Quebec French
    # (tu t͡sy). Read as a code, its suffix names Europe. dicts/arm-w.tsv is
    # the WikiPron Western Armenian list (պապ bɑb), which has its own code.
    # dicts/spa-me.tsv holds the same ipa-dict es_MX readings as dicts/spa.tsv,
    # and the model scores lower with the spa-me prompt, so Spanish requests
    # keep spa.
    MATCH_TAGS = {"srp": "sr-Cyrl", "zho-s": "cmn-Hans", "zho-t": "cmn-Hant", "kur": "ckb",
                  "fra-qu": "fr-CA", "arm-w": "hyw"}

    def __init__(self, model: Optional[str] = None, tokenizer_config: Optional[str] = None,
                 providers: Optional[Sequence[ProviderSpec]] = None,
                 use_cuda=bool(os.environ.get("CUDA", False))):
        """As :class:`ByT5Phonemizer`, with the Charsiu model id when *model* is ``None``."""
        model = model or "Jarbas/charsiu_g2p_multilingual_byT5_tiny_16_layers_100_onnx"
        super().__init__(model, tokenizer_config, providers, use_cuda)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The Charsiu label for *target_lang*, matched through :attr:`MATCH_TAGS`.

        Raises:
            UnsupportedLanguageError: If no label is close enough.
        """
        if _is_hk_cantonese(target_lang):
            return "yue"
        if target_lang.lower() in cls.BYT5_LANGS:
            return target_lang.lower()
        tags = {cls.MATCH_TAGS.get(label, label): label for label in cls.BYT5_LANGS}
        return tags[cls.match_lang(target_lang, list(tags))]

    def phonemize_string(self, text: str, lang: str) -> str:
        # the Charsiu models read one word per prompt
        return " ".join([self._infer_onnx(w, lang) for w in text.split()])


_GRUUT = threading.local()


class _CopyingLookup:
    """Gives each gruut word its own copy of the lexicon pronunciation.

    gruut caches each lexicon pronunciation as one list and gives that list to
    every word that reads it. The French liaison, which Italian also runs, the
    Catalan fusion, elision and diphthong rules, and the Farsi genitive rule
    change the list of the word in place. Without a copy, one "nous allons"
    adds the liaison z to every later "nous" in the process.
    """

    def __init__(self, lookup):
        self.lookup = lookup

    def __call__(self, *args, **kwargs):
        phonemes = self.lookup(*args, **kwargs)
        return None if phonemes is None else list(phonemes)


class GruutPhonemizer(BasePhonemizer):
    """Text to IPA with gruut, which reads and splits whole sentences."""

    engine_distribution = "gruut"
    GRUUT_LANGS = ["en", "ar", "ca", "cs", "de", "es", "fa", "fr", "it",
                   "lb", "nl", "pt", "ru", "sv", "sw"]

    def __init__(self):
        super().__init__(Alphabet.IPA)

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The closest tag of :attr:`GRUUT_LANGS` to *target_lang*.

        Raises:
            UnsupportedLanguageError: If no tag is close enough.
        """
        return cls.match_lang(target_lang, cls.GRUUT_LANGS)

    def _text_to_phonemes(self, text: str, lang: Optional[str] = None):
        """The phonemes of each word, one list per sentence of *text*."""
        lang = self.get_lang(lang)
        try:
            from gruut import TextProcessor
        except ImportError as e:
            raise ImportError(
                "gruut is required for the Gruut phonemizer. "
                "Install it with 'pip install gruut' "
                "(or 'pip install scriptconv[gruut]')."
            ) from e
        # one processor per thread, as gruut.sentences keeps it: the lexicon
        # is a sqlite connection, which only its own thread can use.
        # One processor per language too: gruut reads every sentence after
        # the first, and the part-of-speech tags, with default_lang.
        processors = getattr(_GRUUT, "processors", None)
        if processors is None:
            processors = _GRUUT.processors = {}
        processor = processors.get(lang)
        if processor is None:
            # cache the processor only once its lookup copies: a processor
            # stored before a failed get_settings would leak on the next call
            processor = TextProcessor(default_lang=lang)
            settings = processor.get_settings(lang)
            if settings.lookup_phonemes is not None:
                settings.lookup_phonemes = _CopyingLookup(settings.lookup_phonemes)
            processors[lang] = processor
        graph, root = processor(text, lang=lang)
        for sentence in processor.sentences(graph, root):
            sent_phonemes = [w.phonemes for w in sentence if w.phonemes]
            if sentence and not sent_phonemes:
                raise RuntimeError(f"did you install gruut[{lang}] ?")
            if not sent_phonemes:
                continue
            if sentence.text.endswith("?"):
                sent_phonemes[-1] = ["?"]
            elif sentence.text.endswith("!"):
                sent_phonemes[-1] = ["!"]
            elif sentence.text.endswith(".") or sent_phonemes[-1] == ["‖"]:
                sent_phonemes[-1] = ["."]
            if sent_phonemes:
                yield sent_phonemes

    def phonemize_string(self, text: str, lang: str) -> str:
        pho = ""
        for sent_phonemes in self._text_to_phonemes(text, lang):
            pho += " ".join(["".join(w) for w in sent_phonemes]) + " "
        return pho.strip()


def _stop_goruut_server(process: subprocess.Popen) -> None:
    """Terminate *process*, and kill it after 5 seconds."""
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


class GoruutPhonemizer(BasePhonemizer):
    """Text to IPA with goruut, through pygoruut (https://github.com/neurlang/pygoruut/)."""

    engine_distribution = "pygoruut"
    GORUUT_LANGS_NON_STD = [
        'BengaliDhaka', 'BengaliRahr', 'MalayArab', 'VietnameseCentral', 'VietnameseSouthern',
        'EnglishAmerican', 'EnglishBritish', 'NahuatlClassical', 'Hebrew2', 'Hebrew3',
        'MinnanTawianese', 'MinnanHokkien', 'MinnanTawianese2', 'MinnanHokkien2']
    ISO639 = {
        "af": "Afrikaans",
        "am": "Amharic",
        "ar": "Arabic",
        "az": "Azerbaijani",
        "be": "Belarusian",
        "bn": "Bengali",
        "my": "Burmese",
        "ceb": "Cebuano",
        "ce": "Chechen",
        "zh": "ChineseMandarin",
        "cs": "Czech",
        "da": "Danish",
        "nl": "Dutch",
        "dz": "Dzongkha",
        "en": "English",
        "eo": "Esperanto",
        "fa": "Farsi",
        "fi": "Finnish",
        "fr": "French",
        "de": "German",
        "el": "Greek",
        "gu": "Gujarati",
        "ha": "Hausa",
        "he": "Hebrew",
        "hi": "Hindi",
        "hu": "Hungarian",
        "is": "Icelandic",
        "id": "Indonesian",
        "tts": "Isan",
        "it": "Italian",
        "jam": "Jamaican",
        "ja": "Japanese",
        "jv": "Javanese",
        "kk": "Kazakh",
        "ko": "Korean",
        "lb": "Luxembourgish",
        "mk": "Macedonian",
        "ml": "Malayalam",
        "ms": "MalayLatin",
        "mt": "Maltese",
        "mr": "Marathi",
        "mn": "Mongolian",
        "ne": "Nepali",
        "no": "Norwegian",
        "ps": "Pashto",
        "pl": "Polish",
        "pt": "Portuguese",
        "pa": "Punjabi",
        "ro": "Romanian",
        "ru": "Russian",
        "sk": "Slovak",
        "es": "Spanish",
        "sw": "Swahili",
        "sv": "Swedish",
        "ta": "Tamil",
        "te": "Telugu",
        "th": "Thai",
        "bo": "Tibetan",
        "tr": "Turkish",
        "uk": "Ukrainian",
        "ur": "Urdu",
        "ug": "Uyghur",
        "vi": "VietnameseNorthern",
        "zu": "Zulu",
        "hy": "Armenian",
        "eu": "Basque",
        "bg": "Bulgarian",
        "ca": "Catalan",
        "ny": "Chichewa",
        "hr": "Croatian",
        "et": "Estonian",
        "gl": "Galician",
        "ka": "Georgian",
        "km": "KhmerCentral",
        "lo": "Lao",
        "lv": "Latvian",
        "lt": "Lithuanian",
        "sr": "Serbian",
        "tl": "Tagalog",
        "yo": "Yoruba",
        "sq": "Albanian",
        "an": "Aragonese",
        "as": "Assamese",
        "ba": "Bashkir",
        "bpy": "BishnupriyaManipuri",
        "bs": "Bosnian",
        "chr": "Cherokee",
        "cu": "Chuvash",
        "gla": "GaelicScottish",
        "gle": "GaelicIrish",
        "kl": "Greenlandic",
        "gn": "Guarani",
        "ht": "HaitianCreole",
        "haw": "Hawaiian",
        "io": "Ido",
        "ia": "Interlingua",
        "kn": "Kannada",
        "quc": "Kiche",
        "kok": "Konkani",
        "ku": "Kurdish",
        "ky": "Kyrgyz",
        "qdb": "LangBelta",
        "ltg": "Latgalian",
        "la": "LatinClassical",
        "lat": "LatinEcclesiastical",
        "lfn": "LinguaFrancaNova",
        "jbo": "Lojban",
        "smj": "LuleSaami",
        "mi": "Maori",
        "nah": "NahuatlCentral",
        "nci": "NahuatlMecayapan",
        "ncz": "NahuatlTetelcingo",
        "nog": "Nogai",
        "om": "Oromo",
        "pap": "Papiamento",
        "qu": "Quechua",
        "qya": "Quenya",
        "tn": "Setswana",
        "shn": "ShanTaiYai",
        "sjn": "Sindarin",
        "sd": "Sindhi",
        "si": "Sinhala",
        "sl": "Slovenian",
        "tt": "Tatar",
        "tk": "Turkmen",
        "uz": "Uzbek",
        "cyw": "WelshNorth",
        "cys": "WelshSouth",
        "yue": "Cantonese"
    }

    def __init__(self, remote_url=None):
        super().__init__(Alphabet.IPA)
        try:
            from pygoruut.pygoruut import Pygoruut
            from pygoruut.pygoruut_languages import PygoruutLanguages
        except ImportError as e:
            raise ImportError(
                "pygoruut is required for the Goruut phonemizer. "
                "Install it with 'pip install pygoruut' "
                "(or 'pip install scriptconv[goruut]')."
            ) from e

        self.pygoruut_langs = PygoruutLanguages()
        self._server_finalizer = None
        if remote_url is not None:
            self.pygoruut = Pygoruut(api=remote_url)
        else:
            self.pygoruut = Pygoruut()
            # Pygoruut.__del__ never runs: its stderr drainer thread holds the
            # instance, so the server outlives the process unless stopped here.
            self._server_finalizer = weakref.finalize(
                self, _stop_goruut_server, self.pygoruut.process)

    def close(self) -> None:
        """Stop the local goruut server that this phonemizer started.

        The server also stops when the phonemizer is garbage-collected and at
        interpreter exit. A remote server is never stopped.
        """
        if self._server_finalizer is not None:
            self._server_finalizer()

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The goruut language name for *target_lang*.

        Raises:
            UnsupportedLanguageError: If no language is close enough.
        """
        if target_lang in cls.GORUUT_LANGS_NON_STD:
            return target_lang
        if target_lang.lower() == "en-us":
            return 'EnglishAmerican'
        if target_lang.lower() == "en-gb" or target_lang.lower() == "en-uk":
            return 'EnglishBritish'
        if _is_hk_cantonese(target_lang):
            return cls.ISO639["yue"]
        lang = cls.match_lang(target_lang, list(cls.ISO639))
        return cls.ISO639[lang]

    def phonemize_string(self, text: str, lang: str) -> str:
        # goruut's dicts/<lang>/language.json maps give no stress symbol for a
        # combining acute or grave, so a stress mark only leaves a source-script
        # letter in the IPA or moves the vowel. dicts/arabic and dicts/hebrew3
        # map tashkeel and niqqud, so those marks reach goruut unchanged.
        if _diacritizer_family(lang) == "stress":
            text = strip_diacritics(text, lang)
        lang = self.get_lang(lang)
        return str(self.pygoruut.phonemize(language=lang, sentence=text))


class EpitranPhonemizer(BasePhonemizer):
    """Text to IPA with epitran's per-language maps."""

    engine_distribution = "epitran"
    EPITRAN_LANGS = ['hsn-Latn', 'ful-Latn', 'jpn-Kana', 'tel-Telu', 'nld-Latn', 'aze-Latn', 'amh-Ethi-pp',
                     'msa-Latn', 'spa-Latn-eu', 'ori-Orya', 'bxk-Latn', 'spa-Latn', 'kir-Cyrl', 'lij-Latn', 'kin-Latn',
                     'ces-Latn', 'sin-Sinh', 'urd-Arab', 'vie-Latn', 'gan-Latn', 'fra-Latn', 'nan-Latn', 'kaz-Latn',
                     'swe-Latn', 'jpn-Kana-red', 'tam-Taml', 'sag-Latn', 'csb-Latn', 'pii-latn_Holopainen2019', 'yue-Latn',
                     'got-Latn', 'tur-Latn', 'aar-Latn', 'jav-Latn', 'ita-Latn', 'sna-Latn', 'ilo-Latn', 'tam-Taml-red',
                     'kmr-Latn', 'uzb-Cyrl', 'amh-Ethi', 'mya-Mymr', 'aii-Syrc', 'lit-Latn', 'kmr-Latn-red',
                     'hat-Latn-bab', 'ltc-Latn-bax', 'quy-Latn', 'hau-Latn', 'ood-Latn-alv',
                     'run-Latn', 'orm-Latn', 'ind-Latn', 'kir-Latn', 'mal-Mlym', 'ben-Beng', 'hun-Latn', 'uew',
                     'sqi-Latn', 'jpn-Hira', 'deu-Latn-np', 'xho-Latn', 'fra-Latn-rev', 'fra-Latn-np', 'kaz-Cyrl-bab',
                     'jpn-Hira-red', 'glg-Latn', 'uig-Arab', 'amh-Ethi-red', 'zul-Latn', 'hin-Deva',
                     'uzb-Latn', 'tir-Ethi', 'kaz-Cyrl', 'mlt-Latn', 'deu-Latn-nar', 'est-Latn', 'eng-Latn',
                     'pii-latn_Wiktionary', 'ckb-Arab', 'nya-Latn', 'mon-Cyrl-bab', 'fra-Latn-p', 'ood-Latn-sax',
                     'ukr-Cyrl', 'tgl-Latn', 'lsm-Latn', 'kor-Hang', 'lav-Latn', 'generic-Latn', 'tur-Latn-red',
                     'srp-Latn', 'tir-Ethi-red', 'kbd-Cyrl', 'hrv-Latn', 'srp-Cyrl', 'tpi-Latn', 'khm-Khmr', 'jam-Latn',
                     'ben-Beng-east', 'por-Latn', 'cmn-Latn', 'cat-Latn', 'tha-Thai', 'ara-Arab', 'ben-Beng-red',
                     'fin-Latn', 'hmn-Latn', 'lez-Cyrl', 'fas-Arab', 'lao-Laoo-prereform', 'mar-Deva', 'yor-Latn',
                     'ron-Latn', 'tgl-Latn-red', 'lao-Laoo', 'deu-Latn', 'pan-Guru', 'tuk-Latn', 'tir-Ethi-pp', 'rus-Cyrl',
                     'swa-Latn', 'ceb-Latn', 'wuu-Latn', 'hak-Latn', 'mri-Latn', 'epo-Latn', 'pol-Latn',
                     'tur-Latn-bab', 'kat-Geor', 'tgk-Cyrl', 'aze-Cyrl', 'swa-Latn-red', 'tuk-Cyrl',
                     'nan-Latn-tl', 'zha-Latn', 'cjy-Latn', 'ava-Cyrl', 'som-Latn', 'kir-Arab']

    def __init__(self):
        super().__init__(Alphabet.IPA)
        try:
            import epitran
        except ImportError as e:
            raise ImportError(
                "epitran is required for the Epitran phonemizer. "
                "Install it with 'pip install epitran' "
                "(or 'pip install scriptconv[epitran]')."
            ) from e
        self.epitran = epitran
        self._epis: Dict[str, epitran.Epitran] = {}

    @classmethod
    def get_lang(cls, target_lang: str) -> str:
        """The closest epitran code to *target_lang*.

        Raises:
            ValueError: If no code is close enough, or if the tag is Japanese
                without a Kana or Hira script subtag. A refused Korean tag
                gets a hint to use ko-Hang or kor-Hang.
        """
        # Each epitran Japanese map converts one kana script. Kanji and the
        # other kana script pass through unchanged, so a request for Jpan or
        # Hrkt text would come back half converted.
        subtags = (target_lang or "").replace("_", "-").lower().split("-")
        if subtags[0] in ("ja", "jpn") and not {"kana", "hira"} & set(subtags[1:]):
            raise UnsupportedLanguageError(f"unsupported language code: {target_lang} "
                             "(epitran reads Japanese kana only; use ja-Kana or ja-Hira)")
        try:
            return cls.match_lang(target_lang, cls.EPITRAN_LANGS)
        except ValueError as err:
            # The epitran Korean map converts Hangul only. A bare Korean tag
            # means the Kore script, Hangul plus Hanja, and Hanja passes
            # through unchanged, so the match refuses it.
            if subtags[0] in ("ko", "kor"):
                raise ValueError(f"{err} (epitran reads Korean in Hangul; "
                                 "use ko-Hang or kor-Hang)") from err
            raise

    def phonemize_string(self, text: str, lang: str) -> str:
        lang = self.get_lang(lang)
        # epitran reads English through Flite's lex_lookup; without it, epitran
        # logs a warning and fails with KeyError('') on an empty ARPAbet string
        if lang == "eng-Latn" and shutil.which("lex_lookup") is None:
            raise RuntimeError("epitran English (eng-Latn) needs lex_lookup "
                               "from Flite, and lex_lookup is not on PATH")
        epi = self._epis.get(lang)
        if epi is None:
            epi = self.epitran.Epitran(lang)
            self._epis[lang] = epi
        return epi.transliterate(text)


class PhonetisaurusPhonemizer(BasePhonemizer):
    """WFST grapheme-to-phoneme, through the ``phonetisaurus`` bindings.

    https://github.com/AdolfVonKleist/Phonetisaurus

    Phonetisaurus has no rules and no language list: one trained FST holds
    the language and the symbol set. So:

    * ``model`` is required. scriptconv never downloads a model;
      ``MODEL_SOURCES`` names where published models live.
    * The caller declares ``alphabet``, because the FST does not tell what it
      emits. A CMUdict-trained model emits ARPA, an o2i-trained or
      espeak-trained one emits IPA.
    * There is no language check and no ``LANG_DEFAULTS`` entry.

    ``phonetisaurus`` ships the binaries it drives and the shared objects they
    link against, so applying a model needs no system package. Training also
    needs ``libquadmath.so.0`` from the host GCC runtime (``libquadmath0`` on
    Debian and Ubuntu); this wrapper only applies a model.
    """

    engine_distribution = "phonetisaurus"

    #: Where published FSTs come from. Documentation, never a download.
    MODEL_SOURCES = {
        "rhasspy": "https://github.com/rhasspy/*-g2p (one g2p.fst per language)",
        "cmudict": "trained from CMUdict with 'phonetisaurus train' (ARPA symbols)",
    }

    #: Symbol sets a Phonetisaurus model is known to be trained on. The wrapper
    #: passes the model's symbols through untouched, so this list says which
    #: declarations are meaningful, not which conversions happen.
    SUPPORTED_ALPHABETS = [Alphabet.IPA, Alphabet.ARPA, Alphabet.SAMPA,
                           Alphabet.XSAMPA, Alphabet.GRAPHEMES]

    def __init__(self, model: Optional[str] = None,
                 alphabet: Alphabet = Alphabet.IPA,
                 nbest: int = 1,
                 separator: str = " ",
                 normalizer=None):
        """
        Args:
            model: path to a trained Phonetisaurus FST. Required.
            alphabet: the symbol set the model emits. The caller states it.
            nbest: how many pronunciations the engine ranks per word. The
                best one is returned whatever this is, so a higher value
                changes the search, not the output shape.
            separator: joins the symbols of one word. Models are trained on
                symbol sequences, so the parts need a separator to stay
                readable; pass "" for a bare string.
            normalizer: see :class:`BasePhonemizer`.
        """
        _check_alphabet(self, alphabet, self.SUPPORTED_ALPHABETS)
        super().__init__(alphabet, normalizer=normalizer)
        try:
            import phonetisaurus
        except ImportError as e:
            raise ImportError(
                "phonetisaurus is required for the Phonetisaurus phonemizer. "
                "Install it with 'pip install phonetisaurus' "
                "(or 'pip install scriptconv[phonetisaurus]')."
            ) from e
        if not model or not os.path.isfile(model):
            raise ValueError(
                "Phonetisaurus phonemization needs a local trained FST: pass "
                "model=<path> (scriptconv never downloads — see "
                "MODEL_SOURCES for where published models live)")
        self.phonetisaurus = phonetisaurus
        self.model = model
        self.nbest = nbest
        self.separator = separator

    def phonemize_string(self, text: str, lang: str) -> str:
        """The phonemes of each word of *text*. *lang* is not used: the model decides the language."""
        words = text.split()
        if not words:
            return ""
        # predict() can reorder or drop words, so the result is indexed by
        # word. With nbest > 1 it yields one pair per ranked reading, best
        # first, and the first pair of each word is kept.
        guesses: Dict[str, List[str]] = {}
        for word, symbols in self.phonetisaurus.predict(
                words, self.model, nbest=self.nbest):
            guesses.setdefault(word, symbols)
        return " ".join(self.separator.join(guesses[w])
                        for w in words if w in guesses)


__getattr__ = deprecated_getattr(__name__)
