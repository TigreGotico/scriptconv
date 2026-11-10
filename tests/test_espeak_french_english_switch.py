"""French words espeak-ng reads as English are respelled before it sees them.

espeak-ng 1.52 sends "d'aujourd'hui", "grand'mère" and "prud'homme" to its
English voice. The ``(en)``/``(fr)`` tags are stripped afterwards, so the English
phones stay in the French sentence and a French voice reads them as English.
The respelling tests need no espeak binary; the phoneme tests do.
"""
import shutil

import pytest

from scriptconv.phonemizers.mul import EspeakPhonemizer, _respell_for_espeak


@pytest.mark.parametrize("text, expected", [
    ("d'aujourd'hui", "de aujourd'hui"),
    ("D'aujourd'hui", "De aujourd'hui"),
    ("d’aujourd’hui", "de aujourd'hui"),
    ("Le temps d'aujourd'hui est doux.", "Le temps de aujourd'hui est doux."),
    ("grand'mère", "grand-mère"),
    ("Grand'mères", "Grand-mères"),
    ("grand'mere", "grand-mere"),
    ("prud'homme", "prud-homme"),
    ("Prud'hommes", "Prud-hommes"),
    # All capitals and mixed case (CodeRabbit on scriptconv#160): the case is kept.
    ("D'AUJOURD'HUI", "DE AUJOURD'HUI"),
    ("D\u2019AUJOURD\u2019HUI", "DE AUJOURD'HUI"),
    ("GRAND'MÈRE", "GRAND-MÈRE"),
    ("GRAND'MÈRES", "GRAND-MÈRES"),
    ("Grand'Mère", "Grand-Mère"),
    ("PRUD'HOMMES", "PRUD-HOMMES"),
    ("LE JOUR D'AUJOURD'HUI", "LE JOUR DE AUJOURD'HUI"),
])
def test_the_words_espeak_mistakes_for_english_are_respelled_in_french(text, expected):
    assert _respell_for_espeak(text, "fr") == expected
    assert _respell_for_espeak(text, "fr-ch") == expected


@pytest.mark.parametrize("text", [
    "aujourd'hui", "l'heure", "c'est", "qu'est-ce que c'est", "sommes-nous", "dix-sept",
    "quelqu'un", "jusqu'à demain", "n'est-ce pas",
])
def test_other_french_text_is_left_alone(text):
    assert _respell_for_espeak(text, "fr") == text


def test_other_languages_are_left_alone():
    assert _respell_for_espeak("d'aujourd'hui", "en-us") == "d'aujourd'hui"
    assert _respell_for_espeak("d'aujourd'hui", "it") == "d'aujourd'hui"


needs_espeak = pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="needs the espeak-ng binary")


@needs_espeak
@pytest.mark.parametrize("text", ["d'aujourd'hui", "Le jour d'aujourd'hui", "grand'mère", "les prud'hommes",
                                  "D'AUJOURD'HUI", "GRAND'MÈRE", "PRUD'HOMMES"])
def test_a_french_voice_gets_no_english_phones(text):
    phonemes = EspeakPhonemizer().phonemize_string(text, "fr-FR")
    # the English voice's vowels and affricate, which French never produces here
    assert "ɔː" not in phonemes and "dʒ" not in phonemes and "ɒ" not in phonemes and "ɹ" not in phonemes
