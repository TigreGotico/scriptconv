"""
Russian grapheme-to-phoneme rules and pronunciation-dictionary loader for the
Vosk-TTS voices.

Vendored from ``vosk_tts/g2p.py`` — https://github.com/alphacep/vosk-tts
(Apache-2.0) — so the Vosk Russian front-end is available without the
``vosk-tts`` package at runtime.

``convert`` is a faithful port of ``vosk_tts/g2p.py``: it turns an (optionally
stress-marked) Russian word into the Vosk phoneme inventory — palatalised
consonants get a trailing ``j`` (``bj``, ``tj`` …), vowels carry a stress digit
(``a0`` unstressed, ``a1`` stressed). A ``+`` immediately before a vowel marks
it as stressed; without any ``+`` every vowel is emitted unstressed.

The shipped ``dictionary`` file (word → phonemes) overrides the rules for known
words; ``load_dictionary`` reads both the historical ``word phon…`` layout and
the newer ``word prob phon…`` layout (keeping the highest-probability variant).
The rules alone already produce usable Russian, so the dictionary is optional.
"""
import os
from typing import Dict, List, Optional

# Cyrillic letters that soften the preceding consonant.
softletters = set(u"яёюиье")
# Contexts after which я/ю/е/ё gains a leading glide /j/.
startsyl = set(u"#ъьаяоёуюэеиы-")
# Markers dropped from the final phoneme stream.
others = set(["#", "+", "-", u"ь", u"ъ"])

softhard_cons = {
    u"б": u"b", u"в": u"v", u"г": u"g", u"Г": u"g", u"д": u"d",
    u"з": u"z", u"к": u"k", u"л": u"l", u"м": u"m", u"н": u"n",
    u"п": u"p", u"р": u"r", u"с": u"s", u"т": u"t", u"ф": u"f",
    u"х": u"h",
}

other_cons = {
    u"ж": u"zh", u"ц": u"c", u"ч": u"ch", u"ш": u"sh",
    u"щ": u"sch", u"й": u"j",
}

vowels = {
    u"а": u"a", u"я": u"a", u"у": u"u", u"ю": u"u", u"о": u"o",
    u"ё": u"o", u"э": u"e", u"е": u"e", u"и": u"i", u"ы": u"y",
}


def pallatize(phones: List[tuple]) -> None:
    """In-place: map consonants to their (palatalised) phoneme, looking one
    character ahead to decide whether a soft vowel follows."""
    for i, phone in enumerate(phones[:-1]):
        if phone[0] in softhard_cons:
            if phones[i + 1][0] in softletters:
                phones[i] = (softhard_cons[phone[0]] + "j", 0)
            else:
                phones[i] = (softhard_cons[phone[0]], 0)
        if phone[0] in other_cons:
            phones[i] = (other_cons[phone[0]], 0)


def convert_vowels(phones: List[tuple]) -> List[str]:
    """Emit vowels with their stress digit, inserting a glide /j/ before
    iotated vowels at syllable starts."""
    new_phones: List[str] = []
    prev = ""
    for phone in phones:
        if prev in startsyl:
            if phone[0] in set(u"яюеё"):
                new_phones.append("j")
        if phone[0] in vowels:
            new_phones.append(vowels[phone[0]] + str(phone[1]))
        else:
            new_phones.append(phone[0])
        prev = phone[0]
    return new_phones


def convert(stressword: str) -> str:
    """Convert a (possibly ``+``-stress-marked) Russian word to a
    space-separated Vosk phoneme string."""
    phones = ("#" + stressword + "#")

    # Assign stress marks: a '+' sets the stress flag for the next character.
    stress_phones = []
    stress = 0
    for phone in phones:
        if phone == "+":
            stress = 1
        else:
            stress_phones.append((phone, stress))
            stress = 0

    pallatize(stress_phones)
    phones = convert_vowels(stress_phones)
    phones = [x for x in phones if x not in others]
    return " ".join(phones)


def load_dictionary(path: Optional[str]) -> Dict[str, List[str]]:
    """
    Load a Vosk pronunciation dictionary into a ``word -> [phoneme, …]`` map.

    Handles both file layouts:
      - ``word phon1 phon2 …``            (older voices, e.g. 0.1)
      - ``word prob phon1 phon2 …``       (newer voices; highest prob wins)

    Returns an empty dict when ``path`` is falsy or missing — the rule-based
    :func:`convert` fallback covers any out-of-dictionary word.
    """
    dic: Dict[str, List[str]] = {}
    if not path or not os.path.isfile(path):
        return dic
    probs: Dict[str, float] = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) < 2:
                continue
            word, rest = parts[0], parts[1:]
            # The second column is a probability only when it parses as a float;
            # a real phoneme (a0, sch, …) never does.
            try:
                prob = float(rest[0])
                phones = rest[1:]
            except ValueError:
                prob = None
                phones = rest
            if not phones:
                continue
            if prob is None:
                dic.setdefault(word, phones)
            elif probs.get(word, -1.0) < prob:
                dic[word] = phones
                probs[word] = prob
    return dic
