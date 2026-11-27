"""Sentence rules: what a word's pronunciation owes to its neighbours.

Works on one clause (the words between two punctuation marks):

* sentence stress: function words lose their stress, or keep half of it,
  unless they close the clause (``function_words.txt`` says which);
* "the" and "to" before a vowel;
* linking r: "for" + "all", "after" + "it";
* the flap at the end of "it" and "at" before a vowel.
"""

from dataclasses import dataclass

from .symbols import VOWEL_SET

_SPLIT = {"ɑːɹ": "ɑː", "ɔːɹ": "ɔː", "oːɹ": "oː", "ɪɹ": "ɪ", "ɛɹ": "ɛ", "ʊɹ": "ʊ"}
_RHOTIC = frozenset(("ɚ", "ɜː", "aɪɚ"))
# A slight break precedes these, so nothing links or flaps into them.
_NO_LINK_BEFORE = frozenset(("and", "or", "if"))
_FLAP_BEFORE_VOWEL = frozenset(("it", "at"))


@dataclass
class Unit:
    word: str                       # spelling in lower case; several words for a phrase
    phones: tuple                   # ((phone, stress), ...)
    kind: str = "c"                 # stress class of function_words.txt; "c" = stress as given
    final: tuple = None             # form to use when the word is promoted
    attach: bool = False            # no word boundary before this unit (hyphenated compound)
    source: str = ""                # where the pronunciation came from (for reports)

    @property
    def last_word(self):
        return self.word.rsplit(" ", 1)[-1]

    @property
    def first_word(self):
        return self.word.split(" ", 1)[0]


def unstress(phones):
    return tuple((phone, 0) for phone, _ in phones)


def promote(phones):
    """Give the word a primary stress: on its marked vowel, else on the first vowel."""
    marks = [stress for _, stress in phones]
    if 1 in marks:
        return tuple(phones)
    if 2 in marks:
        target = len(marks) - 1 - marks[::-1].index(2)
    else:
        target = next((i for i, (phone, _) in enumerate(phones) if phone in VOWEL_SET), None)
    return tuple((phone, 1 if i == target else stress) for i, (phone, stress) in enumerate(phones))


def stress_clause(units):
    """Resolve the stress class of every unit of a clause, right to left."""
    primary_follows = False
    for index in range(len(units) - 1, -1, -1):
        unit = units[index]
        promoted = lambda: unit.final if unit.final is not None else promote(unit.phones)
        if unit.kind == "u":
            phones = unstress(unit.phones)
        elif unit.kind == "uf":
            phones = promoted() if index == len(units) - 1 else unstress(unit.phones)
        elif unit.kind == "ur":
            phones = unstress(unit.phones) if primary_follows else promoted()
        elif unit.kind == "s":
            phones = unit.phones if primary_follows else promoted()
        elif unit.kind == "si":
            phones = promoted() if not primary_follows else unit.phones if index == 0 else unstress(unit.phones)
        elif unit.kind == "pf":
            phones = promoted() if index == len(units) - 1 else unit.phones
        else:                                               # "c", "p", "ss": as written
            phones = unit.phones
        unit.phones = tuple(phones)
        marks = {stress for _, stress in unit.phones}
        primary_follows = primary_follows or 1 in marks
    if units and not any(stress for unit in units for _, stress in unit.phones):
        for unit in reversed(units):                        # a clause is never without any stress
            if any(phone in VOWEL_SET for phone, _ in unit.phones):
                unit.phones = promote(unit.phones)
                break


def join_clause(units):
    """Adjust the end of each word to the beginning of the next."""
    for unit, following in zip(units, units[1:]):
        if not unit.phones or not following.phones or following.phones[0][0] not in VOWEL_SET:
            continue
        last, stress = unit.phones[-1]
        if unit.last_word == "the" and last == "ə":
            unit.phones = unit.phones[:-1] + (("ɪ", stress),)
        elif unit.last_word == "to" and last == "ə":
            unit.phones = unit.phones[:-1] + (("ʊ", stress),)
        elif following.first_word in _NO_LINK_BEFORE:
            continue
        elif last in _SPLIT:
            unit.phones = unit.phones[:-1] + ((_SPLIT[last], stress), ("ɹ", 0))
        elif last in _RHOTIC:
            unit.phones = unit.phones + (("ɹ", 0),)
        elif last == "t" and unit.word in _FLAP_BEFORE_VOWEL and len(unit.phones) > 1 and unit.phones[-2][0] in VOWEL_SET:
            unit.phones = unit.phones[:-1] + (("ɾ", 0),)


def groups(units):
    """Units of a clause as spoken words: an attached unit continues the one before."""
    out = []
    for unit in units:
        if unit.attach and out:
            out[-1] = out[-1] + list(unit.phones)
        else:
            out.append(list(unit.phones))
    return [group for group in out if group]
