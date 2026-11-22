"""``Phonemizer.ESPEAK_LT_ACCENT`` resolves to the Lithuanian pitch-accent backend of scriptconv-copyleft.

The backend gives espeak-ng IPA with the three pitch accents (``ˈ``, ``ˌ``,
``ˋ``) from the stress dictionary of Reginutė (RobertasTa/reginute). The two
sentences are FLORES-200 devtest rows 2 and 5 (mteb/flores, revision
69edd3336d102dd184dd531b57defac6c9c60c8f, CC-BY-SA-4.0). The expected symbols
come from the reference implementation, OHF-Voice/piper1-gpl main 39ac0a0
(``LithuanianPhonemizer().phonemize(text)`` of ``piper.phonemize_lithuanian``),
not from this package.
"""
import pytest

from scriptconv.phonemizers import Phonemizer
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY, get_phonemizer

ROWS = [
    ("Kaip ir kai kurie kiti ekspertai, jis skeptiškai vertina galimybę išgydyti diabetą ir atkreipia dėmesį, kad šie duomenys netaikomi sergantiesiems 1 tipo diabetu.",
     ["ˌkaip ˈir kˈai kuˌrʲie kʲɪˋtʲi eksˋpʲertai, ˋjɪs ˋskʲeptʲɪʃkai ˈvʲertʲɪna ɡaɭiˈmʲiːbʲeɑ iɕˈɡiːdʲiːtʲi dʲeˋbʲetaː ˈir atʲkˌrʲeɪpʲe ˌdʲeemʲesiː, kˈat ˌɕie ˈduomʲenʲiːs nʲeˈtaikoːmʲi ˌserɡanʲtʲiesiems vʲˈienas ˋtʲɪpoː dʲebʲeˋtu."]),
    ("Anksčiau „Ring“ vadovas Jamie Siminoffas pastebėjo, kad įmonė buvo įkurta, nes jis negirdėjo savo garaže esančios parduotuvės durų skambučio.",
     ["ankstˌɕeu rʲˈɪnk vaˌdoːvas jˈamʲie simʲinˈoːffas pastʲeˈbʲeejoː, kˈat ˈiːmoːnʲee ˋbuvoː iːkˈurta, nʲˈes ˋjɪs nʲeɡirˈdʲeejoː ˋsavoː ɡaraˋʒe ˌesanʲtɕʲoːs parduoˋtuvʲees ˋduruː skamˋbutɕʲoː."]),
]


def test_the_member_names_the_copyleft_class():
    assert Phonemizer("espeak_lt_accent") is Phonemizer.ESPEAK_LT_ACCENT
    assert PHONEMIZER_REGISTRY[Phonemizer.ESPEAK_LT_ACCENT] == (
        "scriptconv_copyleft.phonemizers.lt", "EspeakLithuanianAccentPhonemizer", "espeak")


@pytest.mark.parametrize("text, expected", ROWS)
def test_gives_the_pitch_accents_of_the_reference(text, expected):
    # one list of symbols per sentence, each symbol one NFD code point
    phonemizer = get_phonemizer(Phonemizer.ESPEAK_LT_ACCENT)
    assert phonemizer.phonemize(text, "lt") == [list(sentence) for sentence in expected]
