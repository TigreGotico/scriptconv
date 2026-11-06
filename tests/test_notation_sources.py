"""The ARPABET and X-SAMPA tables, checked against the sources they cite.

Every ARPABET and X-SAMPA value expected here comes from a source quoted here
and is not read back from ``scriptconv.notation``, so a wrong table entry fails
a test instead of agreeing with itself.

The Lexique, Kirshenbaum, Cotovía and RFE inventories in ``SYMBOLS`` are the
one exception. No source for them is quoted here, so they are the code's own
keys. A failure on such a key proves a flag ``False``, and no key proves it
``True``, so ``test_no_true_flag_rests_on_an_inventory_from_the_code`` holds all
four at ``False``.

ARPABET
    The CMU Pronouncing Dictionary defines the phone set by keyword:

        "The current phoneme set has 39 phonemes, not counting varia due to
        lexical stress. This phoneme (or more accurately, phone) set is based
        on the ARPAbet symbol set developed for speech recognition uses. You
        can find a description of the ARPAbet on Wikipedia, as well information
        on how it relates to the standard IPA symbol set."
        -- http://www.speech.cs.cmu.edu/cgi-bin/cmudict

    The IPA values therefore come from the table that page refers to,
    https://en.wikipedia.org/wiki/ARPABET. Klautau, "ARPABET and the TIMIT
    alphabet" (2001), Fig. 1, reproduces the table of Shoup (1980) and agrees on
    the rows this file corrects: phoneme ɛ is EH, "bet"; ɝ is ER, "bird"; "syl
    l" is EL, "battle". It writes the broad phoneme r for R, "rent". The CMU
    page refers to the narrower ɹ.

X-SAMPA
    J.C. Wells, "Computer-coding the IPA: a proposed extension of SAMPA":

        "What follows is a proposed keyboard-compatible coding for the entire
        set of IPA symbols. It covers everything on the 1993 IPA Chart,
        including diacritics and tone marks"
        "Note that IPA symbols belonging to the ordinary Roman lower-case
        alphabet (e.g. u, x) remain the same. They are not listed below."
        -- https://www.phon.ucl.ac.uk/home/sampa/x-sampa.htm

    Rows quote that page's phonetic labels. The page prints no IPA glyphs, so
    the IPA value of each row is the one https://en.wikipedia.org/wiki/X-SAMPA
    gives for the same spelling. Rows that only the full article has quote
    ipasam-x.pdf, from the same page.

Diacritics above a letter
    "A diacritic may be moved to avoid conflicts of space. One that is normally
    placed below a letter may be moved above it to avoid a descender or another
    diacritic, as with the voiceless ring on ŋ̊ [...]"
    -- https://en.wikipedia.org/wiki/International_Phonetic_Alphabet
"""
import re
import unicodedata

import pytest

from scriptconv import notation
from scriptconv.notation import (
    NOTATION_INFO,
    Notation,
    UnknownSymbolError,
    arpa_to_ipa,
    convert,
    ipa_to_arpa,
    ipa_to_xsampa,
    xsampa_to_ipa,
)

# ---------------------------------------------------------------------------
# ARPABET
# ---------------------------------------------------------------------------

# "Phoneme Example Translation", the whole table from the CMU page.
CMU_PHONES = [
    ("AA", "odd", "AA D"), ("AE", "at", "AE T"), ("AH", "hut", "HH AH T"),
    ("AO", "ought", "AO T"), ("AW", "cow", "K AW"), ("AY", "hide", "HH AY D"),
    ("B", "be", "B IY"), ("CH", "cheese", "CH IY Z"), ("D", "dee", "D IY"),
    ("DH", "thee", "DH IY"), ("EH", "Ed", "EH D"), ("ER", "hurt", "HH ER T"),
    ("EY", "ate", "EY T"), ("F", "fee", "F IY"), ("G", "green", "G R IY N"),
    ("HH", "he", "HH IY"), ("IH", "it", "IH T"), ("IY", "eat", "IY T"),
    ("JH", "gee", "JH IY"), ("K", "key", "K IY"), ("L", "lee", "L IY"),
    ("M", "me", "M IY"), ("N", "knee", "N IY"), ("NG", "ping", "P IH NG"),
    ("OW", "oat", "OW T"), ("OY", "toy", "T OY"), ("P", "pee", "P IY"),
    ("R", "read", "R IY D"), ("S", "sea", "S IY"), ("SH", "she", "SH IY"),
    ("T", "tea", "T IY"), ("TH", "theta", "TH EY T AH"), ("UH", "hood", "HH UH D"),
    ("UW", "two", "T UW"), ("V", "vee", "V IY"), ("W", "we", "W IY"),
    ("Y", "yield", "Y IY L D"), ("Z", "zee", "Z IY"), ("ZH", "seizure", "S IY ZH ER"),
]

# 2-letter code, IPA, example word: the Vowels and Consonants tables of
# https://en.wikipedia.org/wiki/ARPABET. AA is printed there as "ɑ~ɒ".
ARPABET_IPA = [
    ("AA", "ɑ", "balm"), ("AE", "æ", "bat"), ("AH", "ʌ", "buck"),
    ("AO", "ɔ", "caught"), ("AW", "aʊ", "bout"), ("AX", "ə", "comma"),
    ("AXR", "ɚ", "letter"), ("AY", "aɪ", "bite"), ("EH", "ɛ", "bet"),
    ("ER", "ɝ", "bird"), ("EY", "eɪ", "bait"), ("IH", "ɪ", "bit"),
    ("IX", "ɨ", "roses"), ("IY", "i", "beat"), ("OW", "oʊ", "boat"),
    ("OY", "ɔɪ", "boy"), ("UH", "ʊ", "book"), ("UW", "u", "boot"),
    ("UX", "ʉ", "dude"),
    ("B", "b", "buy"), ("CH", "tʃ", "China"), ("D", "d", "die"),
    ("DH", "ð", "thy"), ("DX", "ɾ", "butter"), ("EL", "l̩", "bottle"),
    ("EM", "m̩", "rhythm"), ("EN", "n̩", "button"), ("F", "f", "fight"),
    ("G", "ɡ", "guy"), ("HH", "h", "high"), ("JH", "dʒ", "jive"),
    ("K", "k", "kite"), ("L", "l", "lie"), ("M", "m", "my"), ("N", "n", "nigh"),
    ("NG", "ŋ", "sing"), ("NX", "ɾ̃", "winter"), ("P", "p", "pie"),
    ("Q", "ʔ", "uh-oh"), ("R", "ɹ", "rye"), ("S", "s", "sigh"), ("SH", "ʃ", "shy"),
    ("T", "t", "tie"), ("TH", "θ", "thigh"), ("V", "v", "vie"), ("W", "w", "wise"),
    ("WH", "ʍ", "why"), ("Y", "j", "yacht"), ("Z", "z", "zoo"), ("ZH", "ʒ", "pleasure"),
]
# The table prints "HH or H".
ARPABET_SECOND_SPELLINGS = [("H", "h", "high")]
ARPABET = {code: ipa for code, ipa, _ in ARPABET_IPA}

# The CMU page: "vowels carry a lexical stress marker".
CMU_VOWELS = {"AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY",
              "OW", "OY", "UH", "UW"}


@pytest.mark.parametrize("code, ipa, word", ARPABET_IPA + ARPABET_SECOND_SPELLINGS)
def test_arpabet_value_matches_the_cited_table(code, ipa, word):
    assert arpa_to_ipa(code) == ipa


@pytest.mark.parametrize("code, ipa, word", ARPABET_IPA)
def test_arpabet_value_converts_back(code, ipa, word):
    assert ipa_to_arpa(ipa) == code


def test_every_cmu_phone_has_a_cited_ipa_value():
    assert {phone for phone, _, _ in CMU_PHONES} <= set(ARPABET)
    assert len(CMU_PHONES) == 39


@pytest.mark.parametrize("phone, word, translation", CMU_PHONES)
def test_cmu_keyword_round_trip(phone, word, translation):
    expected = "".join(ARPABET[token] for token in translation.split())
    assert arpa_to_ipa(translation) == expected
    assert ipa_to_arpa(expected) == translation


@pytest.mark.parametrize("ipa, arpa", [
    ("ɛ", "EH"),            # the table's "bet"
    ("ɝ", "ER"),            # the table's "bird"
    ("ɚ", "AXR"),           # the table's "letter"
    ("hɛloʊ", "HH EH L OW"),
    ("bɝd", "B ER D"),
    ("lɛtɚ", "L EH T AXR"),
])
def test_english_vowels_never_become_unknown(ipa, arpa):
    assert ipa_to_arpa(ipa) == arpa


@pytest.mark.parametrize("ipa, arpa", [
    # "In RP, /ɛ/ may be transcribed as /e/", English phonology, Wikipedia.
    # Shoup writes EY as e, so a bare e is ambiguous. This keeps the RP reading.
    ("e", "EH"),
    ("r", "R"),       # Shoup's phoneme for R
    ("ɜr", "ER"),
    ("ər", "AXR"),
    ("ɫ̩", "EL"),
])
def test_broader_input_spellings_stay_accepted(ipa, arpa):
    assert ipa_to_arpa(ipa) == arpa


# CMUdict has no AXR. The cited table gives "letter" as AXR, ɚ, and CMUdict
# spells that word L EH1 T ER0, so unstressed ER is ɚ, as unstressed AH is ə.
@pytest.mark.parametrize("arpa, ipa", [
    ("L EH1 T ER0", "lˈɛtɚ"),    # CMUdict: letter
    ("B ER1 D", "bˈɝd"),         # CMUdict: bird
    ("K AA1 M AH0", "kˈɑmə"),    # CMUdict: comma
])
def test_cmudict_entries_keep_stress_exactly(arpa, ipa):
    assert arpa_to_ipa(arpa, stress=True) == ipa
    assert ipa_to_arpa(ipa, stress=True) == arpa


@pytest.mark.parametrize("arpa", [
    "AH0 R AA1 N AH0 T",     # CMUdict: ahranat
    "AE2 L F AH0 R EH1 D AH0",  # CMUdict: alfareda
])
def test_schwa_before_r_stays_two_phones(arpa):
    assert ipa_to_arpa(arpa_to_ipa(arpa, stress=True), stress=True) == arpa


@pytest.mark.parametrize("ipa, arpa", [
    ("ˈæd ˈhɑk", "AE D HH AA K"),
    ("ə ˈd", "AX D"),
])
def test_a_word_gap_is_not_an_unknown_symbol(ipa, arpa):
    assert ipa_to_arpa(ipa) == arpa


# ---------------------------------------------------------------------------
# X-SAMPA
# ---------------------------------------------------------------------------

# X-SAMPA spelling, IPA, Wells's label, and his second spelling if any.
WELLS_SUMMARY = [
    ("t`", "ʈ", "retroflex plosive, voiceless"),
    ("d`", "ɖ", "retroflex plosive, voiced"),
    ("F", "ɱ", "labiodental nasal"),
    ("n`", "ɳ", "retroflex nasal"),
    ("J", "ɲ", "palatal nasal"),
    ("N", "ŋ", "velar nasal"),
    ("N\\", "ɴ", "uvular nasal"),
    ("B\\", "ʙ", "bilabial trill"),
    ("R\\", "ʀ", "uvular trill"),
    ("4", "ɾ", "alveolar tap"),
    ("r`", "ɽ", "retroflex flap"),
    ("p\\", "ɸ", "bilabial fricative, voiceless"),
    ("B", "β", "bilabial fricative, voiced"),
    ("T", "θ", "dental fricative, voiceless"),
    ("D", "ð", "dental fricative, voiced"),
    ("S", "ʃ", "postalveolar fricative, voiceless"),
    ("Z", "ʒ", "postalveolar fricative, voiced"),
    ("s`", "ʂ", "retroflex fricative, voiceless"),
    ("z`", "ʐ", "retroflex fricative, voiced"),
    ("C", "ç", "palatal fricative, voiceless"),
    ("j\\", "ʝ", "palatal fricative, voiced"),
    ("G", "ɣ", "velar fricative, voiced"),
    ("X", "χ", "uvular fricative, voiceless"),
    ("R", "ʁ", "uvular fricative, voiced"),
    ("X\\", "ħ", "pharyngeal fricative, voiceless"),
    ("?\\", "ʕ", "pharyngeal fricative, voiced"),
    ("h\\", "ɦ", "glottal fricative, voiced"),
    ("K", "ɬ", "alveolar lateral fricative, vl."),
    ("K\\", "ɮ", "alveolar lateral fricative, vd."),
    ("P", "ʋ", "labiodental approximant", "v\\"),
    ("r\\", "ɹ", "alveolar approximant"),
    ("r\\`", "ɻ", "retroflex approximant"),
    ("M\\", "ɰ", "velar approximant"),
    ("l`", "ɭ", "retroflex lateral approximant"),
    ("L", "ʎ", "palatal lateral approximant"),
    ("L\\", "ʟ", "velar lateral approximant"),
    ("O\\", "ʘ", "bilabial"),
    ("|\\", "ǀ", "dental"),
    ("!\\", "ǃ", "(post)alveolar"),
    ("=\\", "ǂ", "palatoalveolar"),
    ("|\\|\\", "ǁ", "alveolar lateral"),
    ("_>", "ʼ", "ejective"),
    ("M", "ɯ", "close back unrounded"),
    ("1", "ɨ", "close central unrounded"),
    ("}", "ʉ", "close central rounded"),
    ("I", "ɪ", "lax i"),
    ("Y", "ʏ", "lax y"),
    ("U", "ʊ", "lax u"),
    ("2", "ø", "close-mid front rounded"),
    ("@\\", "ɘ", "close-mid central unrounded"),
    ("8", "ɵ", "close-mid central rounded"),
    ("7", "ɤ", "close-mid back unrounded"),
    ("@", "ə", "schwa"),
    ("E", "ɛ", "open-mid front unrounded"),
    ("9", "œ", "open-mid front rounded"),
    ("3", "ɜ", "open-mid central unrounded"),
    ("3\\", "ɞ", "open-mid central rounded"),
    ("V", "ʌ", "open-mid back unrounded"),
    ("O", "ɔ", "open-mid back rounded"),
    ("{", "æ", "ash (ae digraph)"),
    ("6", "ɐ", "open schwa (turned a)"),
    ("&", "ɶ", "open front rounded"),
    ("A", "ɑ", "open back unrounded"),
    ("Q", "ɒ", "open back rounded"),
    ("W", "ʍ", "voiceless labial-velar fricative"),
    ("H", "ɥ", "voiced labial-palatal approx."),
    ("H\\", "ʜ", "voiceless epiglottal fricative"),
    ("<\\", "ʢ", "voiced epiglottal fricative"),
    (">\\", "ʡ", "epiglottal plosive"),
    ("s\\", "ɕ", "alveolo-palatal fricative, vl."),
    ("z\\", "ʑ", "alveolo-palatal fricative, voiced"),
    ("l\\", "ɺ", "alveolar lateral flap"),
    ("x\\", "ɧ", "simultaneous S and x"),
    ("\"", "ˈ", "primary stress"),
    ("%", "ˌ", "secondary stress"),
    (":", "ː", "long"),
    (":\\", "ˑ", "half-long"),
    ("_X", "\u0306", "extra-short"),
    ("-\\", "‿", "linking mark"),
    ("_T", "\u030B", "level extra high"),
    ("_H", "\u0301", "level high"),
    ("_M", "\u0304", "level mid"),
    ("_L", "\u0300", "level low"),
    ("_B", "\u030F", "level extra low"),
    ("!", "\uA71C", "downstep"),
    ("^", "\uA71B", "upstep"),
    ("_R", "\u030C", "contour, rising"),
    ("_F", "\u0302", "contour, falling"),
    ("_H_T", "\u1DC4", "contour, high rising"),
    ("_B_L", "\u1DC5", "contour, low rising"),
    ("_R_F", "\u1DC8", "contour, rising-falling"),
    ("<R>", "↗", "global rise"),
    ("<F>", "↘", "global fall"),
    ("_0", "\u0325", "voiceless"),
    ("_v", "\u032C", "voiced"),
    ("_h", "ʰ", "aspirated"),
    ("_O", "\u0339", "more rounded"),
    ("_c", "\u031C", "less rounded"),
    ("_+", "\u031F", "advanced"),
    ("_-", "\u0320", "retracted"),
    ("_\"", "\u0308", "centralized"),
    ("=", "\u0329", "syllabic", "_="),
    ("_^", "\u032F", "non-syllabic"),
    ("`", "\u02DE", "rhoticity"),
    ("_t", "\u0324", "breathy voiced"),
    ("_k", "\u0330", "creaky voiced"),
    ("_N", "\u033C", "linguolabial"),
    ("_w", "ʷ", "labialized"),
    ("'", "ʲ", "palatalized", "_j"),
    ("_G", "ˠ", "velarized"),
    ("_?\\", "ˤ", "pharyngealized"),
    ("_d", "\u032A", "dental"),
    ("_a", "\u033A", "apical"),
    ("_m", "\u033B", "laminal"),
    ("~", "\u0303", "nasalized", "_~"),
    ("_n", "ⁿ", "nasal release"),
    ("_l", "ˡ", "lateral release"),
    ("_}", "\u031A", "no audible release"),
    ("_e", "\u0334", "velarized or pharyngealized"),
    ("5", "ɫ", "velarized l, alternatively"),
    ("_r", "\u031D", "raised"),
    ("_o", "\u031E", "lowered"),
    ("_A", "\u0318", "advanced tongue root"),
    ("_q", "\u0319", "retracted tongue root"),
]

# Symbols the full article has and the summary page does not.
#   Section 15: _x "over-cross, mid-centralized".
#   Section 12: G\ "voiced uvular plosive", J\ "voiced palatal plosive",
#   I\ "central lax close unrounded vowel", U\ "central lax close rounded
#   vowel".
#   Section 3: ? "glottal stop".
#   Section 14: "d_<, J\_<, g_<, G\_<" and b_< are the implosives.
#   Section 6: "/b3`d/" and "@`" are the r-coloured vowels of General American.
#   Section 19: "The minor and major group boundary symbols, | and ||, can
#   remain as they are".
#   Section 23: "e_L_H or e_R or e_/" and "e_H_L or e_F or e_\" are the
#   rising and falling tones.
#   Section 14 and 18: "write ejectives with [_?]".
#   Section 22: "<T>", "<H>", "<M>", "<L>", "<B>", "<BT>", "<TB>", "<HT>",
#   "<BL>", "<HTH>" are the tone letters, "<!>" downstep, "<^>" upstep,
#   "</> or <R>" global rise, "<\> or <F>" global fall.
WELLS_ARTICLE = [
    ("_x", "̽", "mid-centralized"),
    ("G\\", "ɢ", "voiced uvular plosive"),
    ("J\\", "ɟ", "voiced palatal plosive"),
    ("I\\", "ᵻ", "central lax close unrounded vowel"),
    ("U\\", "ᵿ", "central lax close rounded vowel"),
    ("?", "ʔ", "glottal stop"),
    ("b_<", "ɓ", "hooktop b, implosive"),
    ("d_<", "ɗ", "implosive"),
    ("J\\_<", "ʄ", "implosive"),
    ("g_<", "ɠ", "implosive"),
    ("G\\_<", "ʛ", "implosive"),
    ("@`", "ɚ", "r-coloured"),
    ("3`", "ɝ", "General American vowel of bird"),
    ("|", "|", "minor group boundary"),
    ("||", "‖", "major group boundary"),
    ("<T>", "˥", "Extra high, Top pitch"),
    ("<H>", "˦", "High pitch"),
    ("<M>", "˧", "Mid pitch"),
    ("<L>", "˨", "Low pitch"),
    ("<B>", "˩", "Extra low, Bottom pitch"),
    ("<BT>", "˩˥", "Rising"),
    ("<TB>", "˥˩", "Falling"),
    ("<HT>", "˧˥", "High rising"),
    ("<BL>", "˩˧", "Low rising"),
    ("<HTH>", "˧˥˧", "Rising-falling"),
    ("_", "͡", "tie bar"),
]

# Second spellings the article allows, with the first spelling they fold onto.
WELLS_ALTERNATIVES = {"_/": "_R", "_\\": "_F", "_?": "_>", "<!>": "!", "<^>": "^",
                      "</>": "<R>", "<\\>": "<F>",
                      # Wells: "e_L_H or e_R or e_/", "e_H_L or e_F or e_\\",
                      # "e_M_H_L or e_R_F or e_/_\\".
                      "_L_H": "_R", "_H_L": "_F", "_M_H_L": "_R_F", "_/_\\": "_R_F"}

# The Wikipedia table's "syllable break". Wells leaves "." to "indicators of
# pauses and boundaries".
WIKIPEDIA_ONLY = [(".", ".", "syllable break")]

# Wells: "IPA symbols belonging to the ordinary Roman lower-case alphabet (e.g.
# u, x) remain the same." The IPA letter for g is U+0261.
LOWER_CASE = [(c, "ɡ" if c == "g" else c, "lower-case alphabet")
              for c in "abcdefghijklmnopqrstuvwxyz"]

ROWS = [row[:3] for row in WELLS_SUMMARY] + WELLS_ARTICLE + WIKIPEDIA_ONLY + LOWER_CASE
SECOND_SPELLINGS = {row[3]: row[0] for row in WELLS_SUMMARY if len(row) > 3}
SECOND_SPELLINGS.update(WELLS_ALTERNATIVES)
FIRST_SPELLING = {spelling: ipa for spelling, ipa, _ in ROWS}

# Spellings in the sources that stay out of the table, each with its reason.
LEFT_OUT = {
    "<": "Wells: tier escape, \"start prosodic,paralinguistic, or other "
         "nonsegmental notation\". It is a delimiter with no IPA symbol",
    ">": "Wells: tier escape, \"end prosodic etc. notation\". It is a "
         "delimiter with no IPA symbol",
    "_<": "the IPA has no implosive diacritic. Wells pairs _< with five "
          "letters, and those pairs are in the table",
    "_f": "Wikipedia gives _f as global fall. Wells spells that <F>, so _f "
          "reads as the tie bar and f",
    "-": "Wells: an \"explicit disjunctor\". It has no IPA symbol",
    "*": "Wells: SAMPA's conjunctor, \"reserved for special purposes\". It "
         "has no IPA symbol",
    "/": "Wells: a marker of \"vowel archiphonemes or indeterminacies\". It "
         "has no IPA symbol",
    "p_<": "Wells: \"IPA recognition was withdrawn in 1993\"",
    "t_<": "Wells: \"IPA recognition was withdrawn in 1993\"",
    "c_<": "Wells: \"IPA recognition was withdrawn in 1993\"",
    "k_<": "Wells: \"IPA recognition was withdrawn in 1993\"",
    "q_<": "Wells: \"IPA recognition was withdrawn in 1993\"",
    "<LH>": "Wells: \"also <LH>, etc\". Letter by letter it is not the "
            "contour of <BT>, so the two cannot share a value",
    "<HL>": "Wells: \"also <HL> etc\". Letter by letter it is not the "
            "contour of <TB>, so the two cannot share a value",
    "<MHM>": "Wells: \"also <MHM> etc\". Letter by letter it is not the "
             "contour of <HTH>, so the two cannot share a value",
    "_1": "Wells: \"a language-specific tone number\", with six for Cantonese. "
          "Wikipedia: \"The numbers _1 to _6 are reserved diacritics\". It has "
          "no IPA value, so it stays unknown and does not read as a tie",
}

# Spellings no source has.
INVENTED = ["n\\`", "J\\`", "X\\`", "s\\`", "z\\`", "l\\`", "f\\", "-.", "ts`", "dz`"]


def nfd(text):
    return unicodedata.normalize("NFD", text)


@pytest.mark.parametrize("spelling, ipa, label", ROWS)
def test_xsampa_value_matches_the_cited_table(spelling, ipa, label):
    assert nfd(xsampa_to_ipa(spelling, errors="strict")) == nfd(ipa)


@pytest.mark.parametrize("spelling, ipa, label", ROWS)
def test_ipa_value_converts_back_to_the_first_spelling(spelling, ipa, label):
    assert ipa_to_xsampa(ipa, errors="strict") == spelling


@pytest.mark.parametrize("second, first", sorted(SECOND_SPELLINGS.items()))
def test_second_spelling_has_the_value_of_the_first(second, first):
    assert nfd(xsampa_to_ipa(second, errors="strict")) == nfd(FIRST_SPELLING[first])


def test_palatal_and_velar_laterals_are_not_swapped():
    # Wells: L "palatal lateral approximant", "turned y, palatal lateral, It.
    # famiglia". L\ "velar lateral approximant".
    assert xsampa_to_ipa("L") == "ʎ"
    assert xsampa_to_ipa("L\\") == "ʟ"
    assert ipa_to_xsampa("ʎ") == "L"
    assert ipa_to_xsampa("ʟ") == "L\\"


def test_ampersand_is_the_open_front_rounded_vowel():
    # Wells: "capital OE ligature, open fr. rounded V, Dan. drømme".
    assert xsampa_to_ipa("&") == "ɶ"
    assert ipa_to_xsampa("ɶ") == "&"
    assert ipa_to_xsampa("æ") == "{"


@pytest.mark.parametrize("xsampa, ipa", [
    ('fa"miLLa', "faˈmiʎʎa"),      # the article's It. famiglia
    ("X\\A:", "ħɑː"),
    ("EJ\\", "ɛɟ"),
    ("h2:n`", "høːɳ"),
    ("b3`d", "bɝd"),               # the article: "/b3`d/"
    ('"kVl@`', "ˈkʌlɚ"),           # the article: "/"kVl@`/"
    ('ak"t\'abr\'', "akˈtʲabrʲ"),  # the article: "/ak"t'abr'/"
    ("t_S", "t͡ʃ"),           # the article: "/t_S/"
    ("n=", "n̩"),             # the summary: "n= (or n_=)"
    ("A~", "ɑ̃"),             # the summary: "A~ (or A_~)"
    ('<T>"nVT<L>IN', '˥ˈnʌθ˨ɪŋ'),  # the article's "nothing"
    ("ha^na!", "haꜛnaꜜ"),          # the article's hana "flower"
    ("t_?\\", "tˤ"),               # the article: "t_?\"
])
def test_xsampa_strings_from_the_article(xsampa, ipa):
    assert xsampa_to_ipa(xsampa, errors="strict") == ipa
    assert ipa_to_xsampa(ipa, errors="strict") == xsampa


@pytest.mark.parametrize("xsampa, ipa", [
    ("J\\_j\\", "ɟ\u0361ʝ"),   # tie bar, then j\, and not _j and a stray \
    ("d_r\\", "d\u0361ɹ"),      # tie bar, then r\, and not the raising diacritic _r
    ("t_G\\", "t\u0361ɢ"),      # tie bar, then G\, and not the velarizing diacritic _G
])
def test_backslash_takes_priority_over_the_underscore(xsampa, ipa):
    # Wells: "in interpreting the operators \\ and _ we must let \\ take priority".
    assert xsampa_to_ipa(xsampa, errors="strict") == ipa
    assert ipa_to_xsampa(ipa, errors="strict") == xsampa


@pytest.mark.parametrize("ipa, xsampa, back", [
    ("t\u0361θ", "tT", "tθ"),     # t_T would be t with an extra high tone
    ("k\u0361x", "kx", "kx"),     # k_x would be a mid-centralized k
    ("b\u0361v", "bv", "bv"),     # b_v would be a voiced b
    ("ɡ\u0361ɣ", "gG", "ɡɣ"),     # g_G would be a velarized g
    ("q\u0361χ", "qX", "qχ"),     # q_X would be an extra-short q
    ("ʔ\u0361h", "?h", "ʔh"),     # ?_h would be an aspirated glottal stop
    ("t\u0361ʈ", "tt`", "tʈ"),    # t_t` would start with the breathy voice _t
])
def test_tie_is_dropped_where_it_would_read_as_a_diacritic(ipa, xsampa, back):
    # Wells: "it would certainly be more satisfactory to assume affricate
    # status unless an explicit disjunctor (hyphen) is used".
    assert ipa_to_xsampa(ipa, errors="strict") == xsampa
    assert xsampa_to_ipa(xsampa, errors="strict") == back


@pytest.mark.parametrize("ipa, xsampa", [
    ("t\u0361ʃ", "t_S"), ("d\u0361ʒ", "d_Z"), ("t\u0361s", "t_s"), ("d\u0361z", "d_z"),
    ("k\u0361p", "k_p"), ("ɡ\u0361b", "g_b"),
])
def test_tie_stays_where_wells_kept_the_letter_free(ipa, xsampa):
    # Wells: "there is no possible clash: _s, _S, _z, _Z, have been avoided, as
    # have _p and _b and _i, _u, _y."
    assert ipa_to_xsampa(ipa, errors="strict") == xsampa
    assert xsampa_to_ipa(xsampa, errors="strict") == ipa


def test_precomposed_ipa_gives_the_decomposed_result():
    assert ipa_to_xsampa("ã") == "a~"
    assert ipa_to_xsampa("ã") == "a~"
    assert ipa_to_xsampa("ç") == "C"
    assert ipa_to_xsampa("ç") == "C"


def test_tie_bar_below_is_the_tie_bar():
    assert ipa_to_xsampa("t͜ʃ") == "t_S"


@pytest.mark.parametrize("spelling", INVENTED)
def test_invented_spelling_is_gone(spelling):
    assert spelling not in notation._XSAMPA_TO_IPA


def test_every_table_key_is_in_a_cited_source():
    cited = set(FIRST_SPELLING) | set(SECOND_SPELLINGS)
    assert set(notation._XSAMPA_TO_IPA) == cited


@pytest.mark.parametrize("spelling, reason", sorted(LEFT_OUT.items()))
def test_left_out_spelling_stays_out(spelling, reason):
    assert spelling not in notation._XSAMPA_TO_IPA


@pytest.mark.parametrize("spelling", ["ma_1", "ma_2", "ma_3", "ma_4", "a_5", "a_6"])
def test_tone_number_is_unknown_and_not_a_tie(spelling):
    # Wells: "ma_1 rather than as the more explicit ma_H".
    with pytest.raises(UnknownSymbolError):
        xsampa_to_ipa(spelling, errors="strict")
    assert xsampa_to_ipa(spelling) == spelling
    assert xsampa_to_ipa(spelling, errors="replace") == spelling[:-2] + "?"


@pytest.mark.parametrize("ipa, xsampa", [("a\u0361ɨ", "a1"), ("a\u0361ɐ", "a6")])
def test_tie_before_a_tone_number_digit_is_dropped(ipa, xsampa):
    # The underscore there would read as a tone number.
    assert ipa_to_xsampa(ipa) == xsampa


# Wells: "the mid front rounded vowel of Cantonese [...] is IPA [9] = SAMPA [9],
# so outside the range of pitch/tone numbers."
TIE_AND_VOWEL = [("a_7", "a\u0361ɤ"), ("a_8", "a\u0361ɵ"), ("a_9", "a\u0361œ")]


@pytest.mark.parametrize("xsampa, ipa", TIE_AND_VOWEL)
def test_digit_past_the_tone_numbers_is_the_tie_and_a_vowel(xsampa, ipa):
    assert xsampa_to_ipa(xsampa, errors="strict") == ipa


@pytest.mark.parametrize("xsampa, ipa", TIE_AND_VOWEL)
def test_tie_before_a_digit_past_the_tone_numbers_stays(xsampa, ipa):
    assert ipa_to_xsampa(ipa, errors="strict") == xsampa


def test_tie_before_the_letter_f_stays():
    assert xsampa_to_ipa("p_f") == "p\u0361f"


@pytest.mark.parametrize("second, mark", [
    ("_L_H", "\u030C"), ("_H_L", "\u0302"), ("_M_H_L", "\u1DC8"), ("_/_\\", "\u1DC8"),
])
def test_compound_tone_spelling_is_one_mark(second, mark):
    assert xsampa_to_ipa("e" + second, errors="strict") == "e" + mark


@pytest.mark.parametrize("code, ipa, word", ARPABET_IPA)
def test_arpabet_value_has_an_xsampa_spelling(code, ipa, word):
    assert nfd(xsampa_to_ipa(ipa_to_xsampa(ipa, errors="strict"), errors="strict")) == nfd(ipa)


@pytest.mark.parametrize("ipa, xsampa", [("ŋ\u030D", "N="), ("ŋ\u030A", "N_0")])
def test_diacritic_moved_above_a_descender_keeps_its_spelling(ipa, xsampa):
    assert ipa_to_xsampa(ipa, errors="strict") == xsampa


@pytest.mark.parametrize("ipa", ["å", "ɡ\u030A"])
def test_ring_above_stays_unknown_on_other_letters(ipa):
    # å decomposes to a plus the ring above, and it is not an IPA symbol.
    with pytest.raises(UnknownSymbolError):
        ipa_to_xsampa(ipa, errors="strict")


def test_syllabic_eng_reaches_xsampa_from_arpabet():
    assert convert("ENG", "arpa", "x-sampa") == "N="


def test_labiodental_flap_has_no_spelling():
    # U+2C71 joined the IPA after the 1993 chart, so Wells has no spelling.
    with pytest.raises(UnknownSymbolError):
        ipa_to_xsampa("ⱱ", errors="strict")


# ---------------------------------------------------------------------------
# NOTATION_INFO: one definition of lossless
# ---------------------------------------------------------------------------

# The 1993 IPA Chart, as Wells encodes it.
IPA_CHART = sorted({ipa for _, ipa, _ in ROWS})

ARPA_SYMBOLS = sorted(
    {phone for phone, _, _ in CMU_PHONES if phone not in CMU_VOWELS}
    | {phone + digit for phone in CMU_VOWELS for digit in "012"})

SYMBOLS = {
    Notation.ARPA: ARPA_SYMBOLS,
    Notation.XSAMPA: sorted(FIRST_SPELLING) + sorted(SECOND_SPELLINGS),
    Notation.LEXIQUE: sorted(notation._LEXIQUE_TO_IPA),
    Notation.KIRSHENBAUM: sorted(notation._KIRSHENBAUM_TO_IPA),
    Notation.COTOVIA: sorted(notation._COTOVIA_TO_IPA),
    Notation.RFE: sorted(notation._RFE_TO_IPA),
}


CHART_SEQUENCE = re.compile("(?:{})*".format("|".join(
    re.escape(nfd(ipa)) for ipa in sorted(IPA_CHART, key=len, reverse=True))))


def leaves_the_chart(symbol, forward):
    """True when *symbol* fails clause 1 of ``NotationInfo`` towards IPA."""
    try:
        return CHART_SEQUENCE.fullmatch(nfd(forward(symbol, errors="strict"))) is None
    except UnknownSymbolError:
        return True


def breaks_round_trip(symbol, forward, back, expected):
    """True when *symbol* fails clause 2 of ``NotationInfo``."""
    try:
        return nfd(back(forward(symbol, errors="strict"), errors="strict")) != nfd(expected)
    except UnknownSymbolError:
        return True


def to_ipa_failures(notation_key):
    forward = notation._TO_IPA[notation_key]
    back = notation._FROM_IPA[notation_key]
    first = SECOND_SPELLINGS if notation_key is Notation.XSAMPA else {}
    return [s for s in SYMBOLS[notation_key]
            if leaves_the_chart(s, forward)
            or breaks_round_trip(s, forward, back, first.get(s, s))]


def from_ipa_failures(notation_key):
    forward = notation._FROM_IPA[notation_key]
    back = notation._TO_IPA[notation_key]
    return [s for s in IPA_CHART if breaks_round_trip(s, forward, back, s)]


@pytest.mark.parametrize("key", sorted(SYMBOLS, key=lambda n: n.value))
def test_lossless_to_ipa_flag_is_the_measured_round_trip(key):
    assert NOTATION_INFO[key].lossless_to_ipa is (not to_ipa_failures(key))


@pytest.mark.parametrize("key", sorted(SYMBOLS, key=lambda n: n.value))
def test_lossless_from_ipa_flag_is_the_measured_round_trip(key):
    assert NOTATION_INFO[key].lossless_from_ipa is (not from_ipa_failures(key))


def test_every_notation_has_its_flags_measured_or_lacks_a_converter():
    for key, info in NOTATION_INFO.items():
        if key not in SYMBOLS:
            assert (key, info.lossless_to_ipa, info.lossless_from_ipa) == (key, False, False)
            assert key not in notation._TO_IPA or key not in notation._FROM_IPA


def test_kirshenbaum_output_outside_the_chart_is_the_loss():
    # F, K and P round trip under strict, and their output is not IPA.
    assert {"F", "K", "P"} <= set(to_ipa_failures(Notation.KIRSHENBAUM))
    assert notation.kirshenbaum_to_ipa("P", errors="strict") == "\u03A6"


@pytest.mark.parametrize("key", [Notation.LEXIQUE, Notation.KIRSHENBAUM,
                                 Notation.COTOVIA, Notation.RFE])
def test_no_true_flag_rests_on_an_inventory_from_the_code(key):
    assert NOTATION_INFO[key].lossless_to_ipa is False
    assert NOTATION_INFO[key].lossless_from_ipa is False


def test_lexique_is_not_lossless_from_ipa():
    # A French inventory has no spelling for the rest of the chart.
    assert "ʘ" in from_ipa_failures(Notation.LEXIQUE)
    assert NOTATION_INFO[Notation.LEXIQUE].lossless_from_ipa is False


def test_a_pass_through_does_not_count_as_lossless():
    # errors="pass" returns the symbol, so the default round trip holds. The
    # string it returns is not Lexique.
    assert convert(convert("ʘ", "ipa", "lexique"), "lexique", "ipa") == "ʘ"
    assert breaks_round_trip("ʘ", notation.ipa_to_lexique, notation.lexique_to_ipa, "ʘ")


def test_lexique_schwa_pair_is_the_loss_in_the_to_ipa_direction():
    # ° and 3 are two Lexique symbols with one IPA value.
    assert to_ipa_failures(Notation.LEXIQUE) == ["3"]


def test_arpabet_stress_is_the_loss_in_the_to_ipa_direction():
    failures = to_ipa_failures(Notation.ARPA)
    assert "AH1" in failures
    assert all(symbol[-1] in "012" for symbol in failures)


def test_graph_edges_read_the_same_flags():
    from scriptconv.graph import DEFAULT_GRAPH
    for key, info in NOTATION_INFO.items():
        if key in notation._FROM_IPA:
            edge = next(e for e in DEFAULT_GRAPH._edges["ipa"] if e.dst == key.value)
            assert edge.lossless is info.lossless_from_ipa
        if key in notation._TO_IPA:
            edge = next(e for e in DEFAULT_GRAPH._edges[key.value] if e.dst == "ipa")
            assert edge.lossless is info.lossless_to_ipa


# ---------------------------------------------------------------------------
# Whitespace in ipa_to_arpa
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("gap", [" ", "\t", "\n", "\r\n", "\u00A0"])
@pytest.mark.parametrize("errors", ["replace", "strict"])
def test_whitespace_gives_no_token_and_no_word_boundary(gap, errors):
    assert ipa_to_arpa("ɛ" + gap + "ɛ", errors=errors) == "EH EH"
