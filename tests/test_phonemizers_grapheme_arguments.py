"""The character rules of `GraphemePhonemizer` as constructor arguments."""
from types import MappingProxyType

import pytest

from scriptconv.phonemizers.base import GraphemePhonemizer


def _with_attributes(**rules):
    phonemizer = GraphemePhonemizer()
    for name, value in rules.items():
        setattr(phonemizer, name, value)
    return phonemizer


@pytest.mark.parametrize("rules", [
    {"in_word_chars": ""},
    {"replace_chars": MappingProxyType({"-": " ", ";": ","})},
    {"drop_chars": "<>"},
    {"lowercase": False},
])
def test_an_argument_gives_the_output_and_revision_of_the_same_instance_attribute(rules):
    text = "Ela mora em Vila-Real; (perto) <de> Braga: sim."
    by_argument, by_attribute = GraphemePhonemizer(**rules), _with_attributes(**rules)
    assert by_argument.phonemize_string(text, "pt") == by_attribute.phonemize_string(text, "pt")
    assert by_argument.identity("pt").revision == by_attribute.identity("pt").revision


def test_an_empty_in_word_chars_reads_every_hyphen_as_a_space():
    assert GraphemePhonemizer(in_word_chars="").phonemize_string("Ela mora em Vila-Real.", "pt") \
        == "ela mora em vila real."
    assert GraphemePhonemizer().phonemize_string("Ela mora em Vila-Real.", "pt") == "ela mora em vila-real."


def test_no_argument_keeps_the_class_defaults_and_the_revision():
    assert GraphemePhonemizer().identity("pt").revision == GraphemePhonemizer(
        in_word_chars=None, replace_chars=None, drop_chars=None, lowercase=None).identity("pt").revision
    assert "in_word_chars" not in vars(GraphemePhonemizer())


def test_a_replace_chars_argument_is_copied_so_a_later_change_to_the_dict_changes_nothing():
    table = {"-": " "}
    phonemizer = GraphemePhonemizer(replace_chars=table)
    table["-"] = "x"
    assert phonemizer.phonemize_string("a - b", "pt") == "a b"
