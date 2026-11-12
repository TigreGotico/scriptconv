"""espeak-ng stresses the syllable that a combining acute marks in Russian and Ukrainian.

A diacritizer writes the stress as U+0301 after the vowel. The expected
syllable comes from the acute in the input, counted by Cyrillic vowel letters.
The stressed syllable in the output is counted by IPA vowels before "ˈ". The
expected stressed vowel comes from the letter before the acute.
"""
import subprocess

import pytest

from scriptconv.phonemizers import Phonemizer, phonemize
from scriptconv.phonemizers.mul import EspeakPhonemizer

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


# Russian homographs and words that espeak-ng's dictionary stresses elsewhere
RU_MOVED_WORDS = [
    "со́рок", "за́мок", "мука́", "самого́", "жилконто́ра", "по́вестей", "пе́редо", "колоне́ль",
    "го́рода", "сто́ит", "сто́роны", "бе́рега", "вести́", "ноги́", "дома́", "воды́", "орга́н", "тыся́ча",
]
# The IPA that each stressed Russian vowel letter gives. espeak-ng writes ы as
# [y], stressed а and я as [ɑ], and ё after a soft consonant as [ɵ].
STRESSED_VOWELS = {"а": "aɑ", "я": "aɑ", "о": "o", "ё": "oɵ", "е": "eɛ", "э": "ɛe",
                   "и": "iɨy", "ы": "ɨy", "у": "u", "ю": "uʉ"}


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


@pytest.mark.parametrize("lang, word", [("ru-RU", w) for w in RU_WORDS] + [("uk-UA", w) for w in UK_WORDS])
def test_the_primary_stress_falls_on_the_marked_syllable(lang, word):
    ipa = EspeakPhonemizer().phonemize_string(word, lang)
    assert stressed_syllables(ipa) == [marked_syllable(word)], ipa


def test_homographs_in_one_sentence_keep_their_own_stress():
    ipa = EspeakPhonemizer().phonemize_string("Он открыл за́мок, а не замо́к", "ru-RU")
    castle, lock = [w for w in ipa.split() if w.startswith("z")]
    assert stressed_syllables(castle) == [1], ipa
    assert stressed_syllables(lock) == [2], ipa


@pytest.mark.parametrize("word", RU_WORDS + RU_MOVED_WORDS)
def test_the_stressed_vowel_is_the_full_value_of_the_marked_letter(word):
    ipa = EspeakPhonemizer().phonemize_string(word, "ru-RU")
    letter = word[word.index(ACUTE) - 1]
    stressed = next(c for c in ipa.split("ˈ")[1] if c in IPA_VOWELS)
    assert stressed in STRESSED_VOWELS[letter], ipa


@pytest.mark.parametrize("word", RU_WORDS + RU_MOVED_WORDS)
def test_an_unstressed_o_is_reduced(word):
    # akanye: Russian reads an unstressed о as [ʌ] or [ə], never as [o]
    ipa = EspeakPhonemizer().phonemize_string(word, "ru-RU")
    head, tail = ipa.split("ˈ")
    stressed = next(i for i, c in enumerate(tail) if c in IPA_VOWELS)
    assert "o" not in head + tail[:stressed] + tail[stressed + 1:], ipa


@pytest.mark.parametrize("text", ["Он сказал «за́мок» и ушёл.", "Он ушёл (со́рок раз).", "Он сказал +за́мок и ушёл.",
                                  "Он сказал «со́рок» и ушёл."])
def test_a_respelled_word_next_to_a_quote_bracket_or_symbol_is_read(text):
    word = next(w.strip("«»(+.") for w in text.split() if ACUTE in w)
    alone = EspeakPhonemizer().phonemize_string(word, "ru-RU")
    assert alone in EspeakPhonemizer().phonemize_string(text, "ru-RU").split()
    assert alone in phonemize(text, "ru-RU", override=Phonemizer.ESPEAK).split()


@pytest.mark.parametrize("lang, text, word", [
    ("ru-RU", "Он бы́л дома, и е́сть хочет.", "бы́л"),
    ("ru-RU", "Он бы́л дома, и е́сть хочет.", "е́сть"),
    ("ru-RU", "Я знаю, что́ он сказал.", "что́"),
    ("uk-UA", "Він бу́в удома.", "бу́в"),
])
def test_a_stressed_monosyllable_keeps_its_stress_in_a_sentence(lang, text, word):
    words = [w for w in EspeakPhonemizer().phonemize_string(text, lang).split()]
    position = [w.strip(".,") for w in text.split()].index(word)
    assert "ˈ" in words[position], words


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
