"""Enumerations shared across the phonemizer layer.

``Alphabet`` names the symbol set a phonemizer emits; ``Phonemizer`` names the
backend engine.  Both are ``str`` enums whose VALUES are wire format — voice
configuration files store them as plain strings — and must never change.
(Downstream TTS re-exports ``Phonemizer`` under its historical name
``PhonemeType``.)
"""
from enum import Enum


class Alphabet(str, Enum):
    UNICODE = "unicode"
    IPA = "ipa"
    ARPA = "arpa" # en
    SAMPA = "sampa"
    XSAMPA = "x-sampa"
    RFE = "rfe" # https://en.wikipedia.org/wiki/RFE_Phonetic_Alphabet
    HANGUL = "hangul" # ko
    KANA = "kana" # ja
    HIRA = "hira" # ja
    HEPBURN = "hepburn" # ja romanization
    KUNREI = "kunrei" # ja romanization
    NIHON = "nihon" # ja romanization
    PINYIN = "pinyin" # zh
    BOPOMOFO = "bopomofo" # zh (zhuyin) — misaki v1.1 representation
    ERAAB = "eraab" # fa
    COTOVIA = "cotovia" # gl
    HANZI = "hanzi" # zh
    BUCKWALTER = "buckwalter"
    HALABI = "halabi"  # ar — Halabi Arabic-Phonetiser phoneme notation
    CANGJIE = "cangjie" # zh (Cangjie input method)
    VOSK = "vosk" # ru — vosk-tts phoneme inventory (a0, bj, sch ...)
    GRAPHEMES = "graphemes"  # plain text / grapheme input (user-side)
    AFRICA_G2P = "africa_g2p"  # africa-g2p native-orthography phoneme units (400+ African languages)


class Phonemizer(str, Enum):
    UNICODE = "unicode"  # unicode codepoints
    GRAPHEMES = "graphemes" # text characters

    MISAKI = "misaki"  # back-compat dispatcher across misaki languages
    MISAKI_EN = "misaki_en"
    MISAKI_JA = "misaki_ja"
    MISAKI_ZH = "misaki_zh"  # representation follows alphabet: ipa (v1.0) | bopomofo (v1.1)
    MISAKI_KO = "misaki_ko"
    MISAKI_VI = "misaki_vi"
    ESPEAK = "espeak"
    GRUUT = "gruut"
    GORUUT = "goruut"
    EPITRAN = "epitran"
    BYT5 = "byt5"
    CHARSIU = "charsiu"  # technically same as byt5, but needs special handling for whitespace
    TRANSPHONE = "transphone"
    PHONETISAURUS = "phonetisaurus"  # WFST g2p; language and symbols come from the model
    MIRANDESE = "mwl_phonemizer"  # mirandese (o2i specs); voice configs store this value

    DEEPPHONEMIZER = "deepphonemizer" # en
    OPENPHONEMIZER = "openphonemizer" # en
    G2PEN = "g2pen" # en
    DIZIONE = "dizione"  # en-US (CMUdict lexicon, homograph rules, text rules)
    LEOKANI = "leokani"  # en-US (Kokoro/misaki codes; lexicon, ONNX letter-to-sound and context models)
    KOLOKWA = "kolokwa"  # lir, Liberian English (kolokwa-g2p model)

    TUGAPHONE = "tugaphone"  # pt
    G2PFA = "g2pfa"
    OPENJTALK = "openjtalk" # ja
    OPENJTALK_PROSODY = "openjtalk_prosody"  # ja — OpenJTalk IPA with accent rise, fall and phrase marks
    CUTLET = "cutlet" # ja
    PYKAKASI = "pykakasi" # ja
    COTOVIA = "cotovia"  # galician  (no ipa!)
    AHOTTS = "ahotts"  # basque
    PHONIKUD = "phonikud"  # hebrew
    HEBREW_IPA = "hebrew_ipa"  # hebrew — IPA with stress from text that carries niqqud
    TLTK = "tltk"  # thai — TLTK IPA with a tone digit per syllable
    MANTOQ = "mantoq"  # arabic — the mantoq wrapper around Halabi's Arabic-Phonetiser
    HALABI = "halabi"  # arabic — raw Halabi Arabic-Phonetiser, no diacritizer (vowelized input only)
    IQRA = "iqra"  # arabic — Halabi phonetiser output post-processed to the IqraEval phoneme_ref convention
    VIPHONEME = "viphoneme" # vietnamese
    G2PK = "g2pk" # korean
    KOG2PK = "kog2p" # korean
    G2PC = "g2pc" # chinese
    G2PM = "g2pm" # chinese
    G2PW = "g2pw"  # chinese (g2pW polyphone model; pinyin initials, finals and tones)
    PYPINYIN = "pypinyin" # chinese
    XPINYIN = "xpinyin" # chinese
    JIEBA = "jieba" # chinese  (not a real phonemizer!)
    F5TTS_CHAR = "f5tts_char"  # the text as written, one token per character (Habibi-TTS, SILMA TTS)
    F5TTS_PINYIN = "f5tts_pinyin"  # F5-TTS convert_char_to_pinyin: hanzi as pinyin syllables, other characters as written
    VOSK = "vosk"  # russian  (no ipa!)
    SHAMI = "shami"  # Levantine Arabic / English code-switching (ShamiVITS)
    ARBTOK = "arbtok"  # arabic (dialect-aware, undiacritized text; o2i lattice)
    EUSKAPHONE = "euskaphone"  # basque (dialect-aware; o2i lattice)
    BARRANQUENHO = "barranquenho"  # barranquenho (pt/es contact variety; o2i spec)
    ORTHOGRAPHY2IPA = "orthography2ipa"  # multilingual data-driven IPA (o2i lattice)
    AFRICA_G2P = "africa_g2p"  # rule-based G2P for 400+ African languages (native units or IPA)
    GHANA_G2P = "ghana_g2p"  # africa-g2p rules patched for 42 Ghanaian languages (native units or IPA)
    MATOUB_KAB = "matoub_kab"  # kabyle — the rule set agbalu/Matoub-82M was fitted on
