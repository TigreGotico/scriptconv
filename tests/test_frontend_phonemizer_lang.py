"""FrontendConfig.phonemizer_lang: the backend reads one language, the text stages another."""
import pytest

from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
from scriptconv.phonemizers import Alphabet, BasePhonemizer, GraphemePhonemizer, Segment


class Recorder(BasePhonemizer):
    """Phonemes are the characters of the text. Each language the backend reads is recorded."""

    def __init__(self):
        super().__init__(Alphabet.IPA)
        self.langs = []

    def phonemize_string(self, text, lang):
        self.langs.append(lang)
        return text


def recording_frontend(backend=None, **config):
    seen = []

    def normalizer(text, lang):
        seen.append(lang)
        return text

    backend = backend or Recorder()
    frontend = TextFrontend(FrontendConfig(normalizer=normalizer, **config), backend=backend)
    return frontend, backend, seen


def test_the_text_normalises_in_its_language_and_the_backend_reads_its_own():
    frontend, backend, normalised = recording_frontend(lang="tw", phonemizer_lang="lfn")
    frontend.phonemize("Ɛyɛ me dɛ.")
    assert normalised == ["tw"]
    assert set(backend.langs) == {"lfn"}


def test_a_call_in_another_language_phonemizes_in_that_language():
    # a cloning reference in pt, read by a tw voice: pt espeak, not the voice's lfn
    frontend, backend, normalised = recording_frontend(lang="tw", phonemizer_lang="lfn")
    frontend.phonemize("Olá a todos.", Stages(lang="pt-PT"))
    assert normalised == ["pt-PT"]
    assert set(backend.langs) == {"pt-PT"}


def test_without_phonemizer_lang_the_backend_reads_the_text_language():
    frontend, backend, normalised = recording_frontend(lang="tw")
    frontend.phonemize("Ɛyɛ me dɛ.")
    assert normalised == ["tw"] and set(backend.langs) == {"tw"}


def test_the_identity_names_the_backend_language():
    frontend, _, _ = recording_frontend(lang="tw", phonemizer_lang="lfn")
    assert frontend.identity().lang == Recorder().identity("lfn").lang


def test_the_kept_identity_of_one_backend_language_is_not_read_for_another(identity_cache):
    plain = TextFrontend(FrontendConfig(lang="tw"), backend=GraphemePhonemizer())
    mapped = TextFrontend(FrontendConfig(lang="tw", phonemizer_lang="lfn"), backend=GraphemePhonemizer())
    kept = plain.identity()
    assert kept.revision is not None
    identity = mapped.identity()
    assert identity.lang == GraphemePhonemizer().identity("lfn").lang
    assert identity.revision not in (None, kept.revision)


def test_an_en_us_date_with_the_en_espeak_voice():
    text2spoken = pytest.importorskip("text2spoken")
    pytest.importorskip("scriptconv_copyleft")
    from scriptconv.phonemizers import Phonemizer
    from scriptconv.phonemizers.registry import get_phonemizer
    text = "12/11/2025"
    spoken_us, spoken_gb = text2spoken.normalize(text, "en-US"), text2spoken.normalize(text, "en-GB")
    assert spoken_us != spoken_gb
    frontend = TextFrontend(FrontendConfig(lang="en-US", phonemizer_lang="en", phonemizer=Phonemizer.ESPEAK,
                                           normalizer=text2spoken.normalize))
    espeak = get_phonemizer(Phonemizer.ESPEAK, Alphabet.IPA)
    expected = TextFrontend(FrontendConfig(lang="en", phonemizer=Phonemizer.ESPEAK), backend=espeak)
    assert frontend.phonemize(text) == expected.phonemize(spoken_us)


class WholeTextRecorder(Recorder):
    reads_whole_text = True

    def phonemize_segments(self, text, lang):
        self.langs.append(lang)
        yield Segment(tuple(text), ".", True)


def test_a_whole_text_backend_reads_its_own_language():
    frontend, backend, normalised = recording_frontend(WholeTextRecorder(), lang="tw", phonemizer_lang="lfn")
    frontend.phonemize("Ɛyɛ me dɛ. Me ho yɛ.")
    assert normalised == ["tw"]
    assert set(backend.langs) == {"lfn"}

