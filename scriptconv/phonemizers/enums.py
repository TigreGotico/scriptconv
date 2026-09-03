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
    MIRANDESE = "mwl_phonemizer"

    DEEPPHONEMIZER = "deepphonemizer" # en
    OPENPHONEMIZER = "openphonemizer" # en
    G2PEN = "g2pen" # en

    TUGAPHONE = "tugaphone"  # pt
    G2PFA = "g2pfa"
    OPENJTALK = "openjtalk" # ja
    CUTLET = "cutlet" # ja
    PYKAKASI = "pykakasi" # ja
    COTOVIA = "cotovia"  # galician  (no ipa!)
    AHOTTS = "ahotts"  # basque
    PHONIKUD = "phonikud"  # hebrew
    MANTOQ = "mantoq"  # arabic — the mantoq wrapper around Halabi's Arabic-Phonetiser
    HALABI = "halabi"  # arabic — raw Halabi Arabic-Phonetiser, no diacritizer (vowelized input only)
    IQRA = "iqra"  # arabic — Halabi phonetiser output post-processed to the IqraEval phoneme_ref convention
    VIPHONEME = "viphoneme" # vietnamese
    G2PK = "g2pk" # korean
    KOG2PK = "kog2p" # korean
    G2PC = "g2pc" # chinese
    G2PM = "g2pm" # chinese
    PYPINYIN = "pypinyin" # chinese
    XPINYIN = "xpinyin" # chinese
    JIEBA = "jieba" # chinese  (not a real phonemizer!)
    VOSK = "vosk"  # russian  (no ipa!)
    SHAMI = "shami"  # Levantine Arabic / English code-switching (ShamiVITS)
    ARBTOK = "arbtok"  # arabic (dialect-aware, undiacritized text; o2i lattice)
    EUSKAPHONE = "euskaphone"  # basque (dialect-aware; o2i lattice)
    BARRANQUENHO = "barranquenho"  # barranquenho (pt/es contact variety; o2i lattice)
    ORTHOGRAPHY2IPA = "orthography2ipa"  # multilingual data-driven IPA (o2i lattice)
    AFRICA_G2P = "africa_g2p"  # rule-based G2P for 400+ African languages (native units or IPA)
