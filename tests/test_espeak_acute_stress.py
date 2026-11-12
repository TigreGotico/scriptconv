"""espeak-ng stresses the syllable that a combining acute marks in Russian and Ukrainian.

A diacritizer writes the stress as U+0301 after the vowel. The expected
syllable comes from the acute in the input, counted by Cyrillic vowel letters.
The stressed syllable in the output is counted by IPA vowels before "ˈ".
"""
import shutil
import subprocess

import pytest

from scriptconv.phonemizers.mul import EspeakPhonemizer

needs_espeak = pytest.mark.skipif(shutil.which("espeak-ng") is None, reason="needs the espeak-ng binary")

ACUTE = "\u0301"
CYRILLIC_VOWELS = set("аеёиоуыэюяіїє")
IPA_VOWELS = set("iyɨʉɯuɪʏʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒ")

RU_WORDS = [
    # 1st syllable
    "ты́сяча", "три́дцать", "мы́ло", "ви́шня", "два́дцать", "со́рок", "две́сти", "три́ста",
    "се́мьдесят", "во́семьдесят", "де́вять", "о́блако", "за́мок", "му́ка", "го́род", "ско́лько",
    # 2nd syllable
    "четы́ре", "четы́реста", "пятна́дцать", "двена́дцать", "оди́ннадцать", "доро́га", "соба́ка",
    "карти́на", "учи́тель", "сего́дня",
    # 3rd syllable, not the last
    "девяно́сто", "восемна́дцать", "девятна́дцать",
    # last syllable
    "пятьсо́т", "шестьсо́т", "восемьсо́т", "девятьсо́т", "пятьдеся́т", "молоко́", "голова́",
    "университе́т", "челове́к", "хорошо́", "замо́к", "мука́", "рука́", "окно́", "вода́",
]
UK_WORDS = [
    # 1st syllable
    "ти́сяча", "три́дцять", "со́рок", "два́дцять", "ві́сім", "ві́сімдесят", "п'я́тниця", "кни́жка",
    # 2nd syllable
    "двана́дцять", "оди́надцять", "чоти́ри", "соба́ка", "доро́га", "вівто́рок", "субо́та", "неді́ля",
    # 3rd syllable, not the last
    "дев'яно́сто", "понеді́лок",
    # last syllable
    "п'ятсо́т", "шістдеся́т", "четве́р", "середа́", "вікно́", "рука́", "молоко́",
]


def marked_syllable(word: str) -> int:
    head = word[:word.index(ACUTE)]
    return sum(c.lower() in CYRILLIC_VOWELS for c in head)


def stressed_syllables(ipa: str) -> list:
    """The 1-based syllable of each "ˈ" in one IPA word."""
    return [sum(c in IPA_VOWELS for c in ipa[:i]) + 1 for i, c in enumerate(ipa) if c == "ˈ"]


def espeak(text: str, voice: str) -> str:
    return subprocess.run(["espeak-ng", "-q", "-x", "--ipa", "-v", voice], input=text,
                          capture_output=True, text=True, check=True).stdout.strip()


def test_the_word_lists_cover_first_second_third_and_last_syllables():
    for words in (RU_WORDS, UK_WORDS):
        positions = {marked_syllable(w) for w in words}
        assert {1, 2, 3} <= positions
        assert any(marked_syllable(w) == sum(c in CYRILLIC_VOWELS for c in w) >= 3 for w in words)
    assert len(RU_WORDS) + len(UK_WORDS) >= 30


@needs_espeak
@pytest.mark.parametrize("lang, word", [("ru-RU", w) for w in RU_WORDS] + [("uk-UA", w) for w in UK_WORDS])
def test_the_primary_stress_falls_on_the_marked_syllable(lang, word):
    ipa = EspeakPhonemizer().phonemize_string(word, lang)
    assert stressed_syllables(ipa) == [marked_syllable(word)], ipa


@needs_espeak
def test_homographs_in_one_sentence_keep_their_own_stress():
    ipa = EspeakPhonemizer().phonemize_string("Он открыл за́мок, а не замо́к", "ru-RU")
    castle, lock = [w for w in ipa.split() if w.startswith("z")]
    assert stressed_syllables(castle) == [1], ipa
    assert stressed_syllables(lock) == [2], ipa


@needs_espeak
@pytest.mark.parametrize("lang, voice, word", [("ru-RU", "ru", "что́"), ("ru-RU", "ru", "я́"), ("uk-UA", "uk", "бу́в")])
def test_a_stressed_monosyllable_reads_as_the_bare_word(lang, voice, word):
    assert EspeakPhonemizer().phonemize_string(word, lang) == espeak(word.replace(ACUTE, ""), voice)


@needs_espeak
@pytest.mark.parametrize("lang, voice, text", [
    ("ru-RU", "ru", "Тысяча двести тридцать четыре человека пришли сегодня."),
    ("uk-UA", "uk", "Тисяча двісті тридцять чотири, п'ятниця."),
    # a decomposed é is an acute after a vowel, and only ru and uk read it as stress
    ("pt-PT", "pt", "O cafe\u0301 esta\u0301 quente."),
    ("en-US", "en-us", "The cafe\u0301 is open."),
    # an acute after a Latin letter in Russian text is no Cyrillic stress mark
    ("ru-RU", "ru", "Это cafe\u0301 на углу."),
])
def test_other_text_reaches_espeak_unchanged(lang, voice, text):
    assert EspeakPhonemizer().phonemize_string(text, lang) == espeak(text, voice)
