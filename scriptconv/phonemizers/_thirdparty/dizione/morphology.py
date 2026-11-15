"""Words the dictionary lacks but can be built from words it has.

Plurals, possessives, -ed, -ing, -ly and other regular endings, a few
prefixes, compounds of two dictionary words and British spellings. The stem's
pronunciation comes from the dictionary; the ending is added by rule, with the
adjustments English makes at the seam (the flap of "waited", the r of
"starring", the voicing of "dogs" against "cats").
"""

import re

from .symbols import VOWEL_SET

_SHORT_STEM = re.compile(r"(?:^|[^aeiou])[aeiou](?:[bcdfgklmnprstvz]|th)$")
_SIBILANT = frozenset(("s", "z", "ʃ", "ʒ", "tʃ", "dʒ"))
_VOICELESS = frozenset(("p", "t", "k", "f", "θ", "ʔ"))
_SPLIT = {"ɑːɹ": "ɑː", "ɔːɹ": "ɔː", "oːɹ": "oː", "ɪɹ": "ɪ", "ɛɹ": "ɛ"}
_RHOTIC = frozenset(("ɚ", "ɜː", "aɪɚ", "ʊɹ"))
_CONSONANT_LETTERS = frozenset("bcdfghjklmnpqrstvwxz")
P = lambda *phones: tuple((phone, 0) for phone in phones)

# Endings that leave the stem's stress alone: spelling, phones.
_ENDINGS = (
    ("fully", P("f", "əl", "i")), ("lessly", P("l", "ə", "s", "l", "i")), ("ness", P("n", "ə", "s")),
    ("less", P("l", "ə", "s")), ("ments", P("m", "ə", "n", "t", "s")), ("ment", P("m", "ə", "n", "t")),
    ("ful", P("f", "əl")), ("ship", (("ʃ", 0), ("ɪ", 2), ("p", 0))), ("hood", (("h", 0), ("ʊ", 2), ("d", 0))),
    ("like", (("l", 0), ("aɪ", 2), ("k", 0))), ("dom", P("d", "ə", "m")), ("ish", P("ɪ", "ʃ")),
    ("able", P("ə", "b", "əl")), ("ism", P("ɪ", "z", "ə", "m")), ("ist", P("ɪ", "s", "t")),
    ("wards", P("w", "ɚ", "d", "z")), ("ward", P("w", "ɚ", "d")), ("age", P("ɪ", "dʒ")),
    ("ers", P("ɚ", "z")), ("er", P("ɚ",)), ("est", P("ɪ", "s", "t")), ("y", P("i",)),
)
# Prefix spelling -> (form before a stem stressed on its first syllable, form otherwise).
_PREFIXES = (
    ("under", ((("ʌ", 2), ("n", 0), ("d", 0), ("ɚ", 0)),) * 2), ("over", ((("oʊ", 2), ("v", 0), ("ɚ", 0)),) * 2),
    ("anti", ((("æ", 2), ("n", 0), ("t", 0), ("i", 0)),) * 2), ("semi", ((("s", 0), ("ɛ", 2), ("m", 0), ("i", 0)),) * 2),
    ("non", ((("n", 0), ("ɑː", 2), ("n", 0)),) * 2), ("out", ((("aʊ", 2), ("t", 0)),) * 2),
    ("dis", (P("d", "ɪ", "s"), (("d", 0), ("ɪ", 2), ("s", 0)))), ("mis", (P("m", "ɪ", "s"), (("m", 0), ("ɪ", 2), ("s", 0)))),
    ("un", (P("ʌ", "n"), (("ʌ", 2), ("n", 0)))), ("in", (P("ɪ", "n"), (("ɪ", 2), ("n", 0)))),
    ("re", (P("ɹ", "ᵻ"), (("ɹ", 0), ("iː", 2)))), ("pre", ((("p", 0), ("ɹ", 0), ("iː", 2)),) * 2),
)
_BRITISH = (("isation", "ization"), ("ising", "izing"), ("ised", "ized"), ("ises", "izes"), ("ise", "ize"), ("yse", "yze"),
            ("our", "or"), ("ourable", "orable"), ("ours", "ors"), ("oured", "ored"), ("ouring", "oring"),
            ("tre", "ter"), ("tres", "ters"), ("bre", "ber"), ("ence", "ense"), ("ogue", "og"), ("mme", "m"),
            ("lled", "led"), ("lling", "ling"), ("ller", "ler"), ("oul", "ol"), ("ae", "e"), ("enqui", "inqui"))


def join(stem, ending):
    """Stem + ending, adjusted at the seam."""
    stem = list(stem)
    if not stem or not ending:
        return tuple(stem) + tuple(ending)
    (last, stress), (first, first_stress) = stem[-1], ending[0]
    if first in VOWEL_SET:
        if last in _SPLIT:
            stem[-1:] = [(_SPLIT[last], stress), ("ɹ", 0)]                    # star + ing
        elif last in _RHOTIC:
            stem.append(("ɹ", 0))                                            # wander + ing, sure + er
        elif last == "t" and len(stem) > 1 and (stem[-2][0] in VOWEL_SET or stem[-2][0] == "ɹ") and not first_stress \
                and not (first == "ə" and len(ending) > 1 and ending[1][0] == "n"):
            stem[-1] = ("ɾ", 0)                                              # wait + ed
        elif last == "i":
            stem[-1] = ("ɪ", stress) if first != "ɪ" else ("i", stress)      # storm·y + er; carry + ing
    elif last == "i" and first in ("n", "l", "f", "m"):
        stem[-1] = ("ɪ", stress)                                             # happi + ness, happi + ly
    elif last == "n" and first in ("k", "ɡ"):
        stem[-1] = ("ŋ", 0)
    return tuple(stem) + tuple(ending)


def plural(stem):
    last = stem[-1][0]
    return join(stem, P("ᵻ", "z") if last in _SIBILANT else P("s") if last in _VOICELESS else P("z"))


def past(stem):
    last = stem[-1][0]
    if last in ("t", "d", "ɾ"):
        return join(stem, P("ᵻ", "d"))
    return join(stem, P("t") if last in _VOICELESS or last in ("s", "ʃ", "tʃ") else P("d"))


def adverb(stem):
    last = stem[-1][0]
    return join(stem, P("i") if last in ("əl", "l") else P("l", "i"))


def _stems(body):
    """Spellings the stem may have had before an ending starting with a vowel."""
    out = [body]
    if len(body) > 2 and body[-1] == body[-2] and body[-1] in _CONSONANT_LETTERS:
        out.append(body[:-1])                                                # stopp-ed
    if body and body[-1] in _CONSONANT_LETTERS | {"u"}:
        # A short vowel before a single consonant would have doubled it ("hopped"),
        # so "hoped" and "clothed" come from "hope" and "clothe".
        single = _SHORT_STEM.search(body) is not None
        out.insert(0 if single else len(out), body + "e")                    # lov-ed, spong-ing
    if body.endswith("i") and len(body) > 2:
        out.append(body[:-1] + "y")                                          # stormi-er
    return out


def _secondary(phones):
    """Demote the primary stress of the second part of a compound."""
    return tuple((phone, 2 if stress == 1 else stress) for phone, stress in phones)


def compound(first, second):
    """Two words said as one: the second keeps only a lesser stress ("sandpiper")."""
    return join(first, _secondary(second))


def derive(word, lookup, part=None, depth=0):
    """Pronunciation of ``word`` from a shorter dictionary word, or ``None``.

    ``lookup(spelling)`` returns the dictionary pronunciation or ``None``;
    ``part(spelling)`` does the same for a word that may be half of a compound
    (by default any dictionary word).
    """
    part = part or lookup

    def stem(spelling):
        if len(spelling) < 2:
            return None
        return lookup(spelling) or (derive(spelling, lookup, part, depth + 1) if depth < 2 else None)

    def first(candidates, build):
        for spelling in candidates:
            found = stem(spelling)
            if found:
                return build(found)
        return None

    if word.endswith("'s"):
        return first([word[:-2]], plural)
    if word.endswith("s'"):
        return first([word[:-1]], lambda found: found)
    if word.endswith("ies") and len(word) > 4:
        found = first([word[:-3] + "y"], plural)
        if found:
            return found
    if word.endswith("ves") and len(word) > 4:
        found = first([word[:-3] + "f", word[:-3] + "fe"], lambda f: join(f[:-1] + (("v", 0),), P("z")) if f[-1][0] == "f" else None)
        if found:
            return found
    if word.endswith("es") and len(word) > 3:
        found = first([word[:-2]] if word[-3] in "sxzh" else [], plural)
        if found:
            return found
    if word.endswith("s") and not word.endswith(("ss", "us", "is")) and len(word) > 3:
        found = first([word[:-1]], plural)
        if found:
            return found
    if word.endswith("ied") and len(word) > 4:
        found = first([word[:-3] + "y"], past)
        if found:
            return found
    if word.endswith("ed") and len(word) > 3:
        found = first(_stems(word[:-2]), past)
        if found:
            return found
    if word.endswith("ing") and len(word) > 4:
        found = first(_stems(word[:-3]), lambda f: join(f, P("ɪ", "ŋ")))
        if found:
            return found
    if word.endswith("ily") and len(word) > 4:
        found = first([word[:-3] + "y"], adverb)
        if found:
            return found
    if word.endswith("ly") and len(word) > 3:
        found = first([word[:-2], word[:-2] + "le", word[:-1] + "e"] if word.endswith("bly") or word.endswith("ply")
                      else [word[:-2]], adverb)
        if found:
            return found
    for spelling, phones in _ENDINGS:
        if word.endswith(spelling) and len(word) - len(spelling) > 2:
            body = word[:-len(spelling)]
            if spelling == "y" and body[-1] not in _CONSONANT_LETTERS:
                continue                                                     # "copay" is not "copa" + y
            vowel_first = phones[0][0] in VOWEL_SET
            found = first(_stems(body) if vowel_first else [body[:-1] + "y", body] if body.endswith("i") else [body],
                          lambda f, phones=phones: join(f, phones))
            if found:
                return found
    for spelling, (plain, stressed) in _PREFIXES:
        if word.startswith(spelling) and len(word) - len(spelling) > 2:
            found = stem(word[len(spelling):])
            if found:
                vowels = [stress for phone, stress in found if phone in VOWEL_SET]
                head = plain if vowels and vowels[0] == 1 else stressed
                return join(head, found)
    for old, new in _BRITISH:
        if old in word:
            found = stem(word.replace(old, new, 1))
            if found:
                return found
    if depth == 0:
        # Two dictionary words of four letters or more: "sandpiper", "houseplant".
        # Shorter halves turn up by chance too often ("couplet" is not "coup" + "let").
        best = None
        for cut in range(4, len(word) - 3):
            left, right = part(word[:cut]), part(word[cut:])
            if left and right:
                score = min(cut, len(word) - cut)
                if best is None or score > best[0]:
                    best = (score, left, right)
        if best:
            return compound(best[1], best[2])
    return None
