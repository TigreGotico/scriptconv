"""The Mirandese and Barranquenho backends run on the orthography2ipa specs.

Neither backend imports ``mwl_phonemizer`` or ``g2p_barranquenho``. Every test
blocks both modules, so an import of either raises ``ImportError``.

The expected IPA is copied from the orthography2ipa gold files
``data/gold/portuguese_tts/<spec>.tsv``, by row id, and not from engine output.
"""
import sys
import tomllib
from pathlib import Path

import pytest

from scriptconv.phonemizers import Phonemizer, get_phonemizer
from scriptconv.phonemizers.mwl import MirandesePhonemizer
from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
from scriptconv.phonemizers.pt import BarranquenhoPhonemizer

ROOT = Path(__file__).resolve().parent.parent
ARCHIVED = ("mwl_phonemizer", "g2p_barranquenho")

# (lang, orthography2ipa spec, gold row id, sentence, gold IPA)
MIRANDESE_GOLD = [
    ("mwl", "mwl", "mwl-001",
     "Hoije nun stá friu, mas manhana bai a chober.",
     "ˈojʒɨ ˈnũ ˈs̺ta ˈfɾiw ˈmaz̺ mɐˈɲanɐ ˈβaj ɐ tʃuˈβeɾ"),
    ("mwl-x-sendim", "mwl-x-sendim", "mwl-x-sendim-003",
     "Bou a l doutor l lhunes a la tarde.",
     "ˈbɵw ɐ ɫ dɵwˈtoɾ ɫ ˈlunɨs̺ ɐ lɐ ˈtaɾðɨ"),
    ("mwl-x-ifanes", "mwl-x-ifanes", "mwl-x-ifanes-013",
     "Buonas tardes, cumo stás? Stou bien, grácias.",
     "ˈbʊnɐs̺ ˈtaɾðɨs̺ ˈkumu ˈs̺tas̺ ˈs̺tɵw ˈβjɪ̃ ˈɡɾasjas̺"),
]
BARRANQUENHO_GOLD = [
    ("ext-PT-x-barrancos", "ext-PT-x-barranco", "ext-PT-x-barrancos-006",
     "A sopa de tomate ehtava mehmu boa.",
     "ɐ ˈsopɐ dɨ tuˈmat ehˈtabɐ ˈmɛhmu ˈboɐ"),
]


@pytest.fixture(autouse=True)
def archived_packages_missing(monkeypatch):
    for name in ARCHIVED:
        monkeypatch.setitem(sys.modules, name, None)


@pytest.mark.parametrize("lang, spec, row, text, gold", MIRANDESE_GOLD)
def test_mirandese_reads_the_gold_row(lang, spec, row, text, gold):
    out = MirandesePhonemizer().phonemize_string(text, lang)
    assert out == gold
    assert out == Orthography2IPAPhonemizer().phonemize_string(text, spec)


@pytest.mark.parametrize("lang, spec, row, text, gold", BARRANQUENHO_GOLD)
def test_barranquenho_reads_the_gold_row(lang, spec, row, text, gold):
    out = BarranquenhoPhonemizer().phonemize_string(text, lang)
    assert out == gold
    assert out == Orthography2IPAPhonemizer().phonemize_string(text, spec)


def test_the_registry_builds_both_backends():
    assert isinstance(get_phonemizer(Phonemizer.MIRANDESE), MirandesePhonemizer)
    assert isinstance(get_phonemizer(Phonemizer.BARRANQUENHO), BarranquenhoPhonemizer)


@pytest.mark.parametrize("phonemizer, lang, spec, backend", [
    (MirandesePhonemizer, "mwl-x-sendim", "mwl-x-sendim", "mwl_phonemizer"),
    (BarranquenhoPhonemizer, "ext-PT-x-barrancos", "ext-PT-x-barranco", "barranquenho"),
])
def test_identity_names_the_orthography2ipa_engine(phonemizer, lang, spec, backend):
    identity = phonemizer().identity(lang)
    engine = Orthography2IPAPhonemizer().identity(spec)
    assert (identity.distribution, identity.version, identity.revision) == \
        (engine.distribution, engine.version, engine.revision)
    assert (identity.backend, identity.lang) == (backend, lang)


def test_no_extra_installs_an_archived_package():
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"]["optional-dependencies"]
    named = {dep.lower().replace("-", "_") for deps in extras.values() for dep in deps}
    assert not {dep for dep in named if dep.startswith(ARCHIVED)}
    assert extras["mwl"] == ["scriptconv[o2i]"]
