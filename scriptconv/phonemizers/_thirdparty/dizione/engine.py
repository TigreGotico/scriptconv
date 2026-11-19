"""The phonemizer: text -> spoken words of phones, clause by clause.

Order of authority for one word:
  1. pronunciation written inline in the text
  2. the user's override list
  3. the built-in exception list (``data/exceptions.txt``); a name of several
     words listed there or by the user is spoken with the stress written
  4. function words and function-word groups (sentence level)
  5. the dictionary built from CMUdict
  6. regular endings, prefixes and compounds of dictionary words
  7. names in "-leigh" and words in "-virus", put together from their parts
  8. the unknown-word model
"""

import json
import os
from pathlib import Path
import re

from . import morphology, normalize, sentence, tables
from .align import Aligner
from .convert import convert, from_text, settle_stress
from .g2p import Model
from .homographs import Homographs
from .sentence import Unit

ENVIRONMENT = "DIZIONE_DATA"
OVERRIDES_ENVIRONMENT = "DIZIONE_OVERRIDES"
_LETTER_NAMES = None
_LEIGH = re.compile(r"(?<=[a-z]{2})leigh(?=s?$)")
_VIRUS = ("viruses", "virus")


def default_directory():
    """Where the built files live: ``$DIZIONE_DATA`` or ``built`` inside the package."""
    return Path(os.environ.get(ENVIRONMENT) or Path(__file__).parent / "built")


class Phonemizer:
    def __init__(self, directory=None, overrides=None, join_phrases=True):
        self.directory = Path(directory) if directory else default_directory()
        lexicon = self.directory / "lexicon.tsv"
        if not lexicon.exists():
            raise FileNotFoundError(
                f"no phonemizer data in {self.directory}: build it with scripts/build.sh"
                f"or point ${ENVIRONMENT} at a built directory")
        self.lexicon = dict(line.split("\t", 1) for line in lexicon.read_text(encoding="utf-8").splitlines() if line)
        self.aligner = Aligner(json.loads((self.directory / "align.json").read_text(encoding="utf-8")))
        self.model = Model(self.directory) if (self.directory / "g2p.npz").exists() else None
        self.homographs = Homographs(self.directory / "homographs.json") if (self.directory / "homographs.json").exists() else None
        self.functions = tables.function_words()
        self.phrases = tables.phrases() if join_phrases else {}
        self.phrase_length = max((len(key) for key in self.phrases), default=1)
        self.exceptions = tables.pronunciations("exceptions.txt")
        self.names = tables.names("exceptions.txt")         # names of several words, with their own rhythm
        self.name_starts = {key[0] for key in self.names}
        self.name_length = max((len(key) for key in self.names), default=1)
        self.user_names = set()
        self.overrides = {}
        override_file = os.environ.get(OVERRIDES_ENVIRONMENT)
        if override_file:
            self.add_overrides(Path(override_file))
        if overrides:
            self.add_overrides(overrides)
        self.normalizer = normalize.Normalizer(self.is_word)
        self._cache = {}

    # ---- single words -------------------------------------------------

    def add_overrides(self, source):
        """Pronunciations that win over everything else. ``source`` is a
        dictionary ``{word: pronunciation}``, a path, or the text of a table;
        a pronunciation is CMUdict notation or phones with stress marks. A
        name of several words takes one pronunciation per word, separated by
        ``|``: ``{"tung tung tung sahur": "T UW1 NG | T UW2 NG | T UW2 NG | S AA0 HH UH1 R"}``."""
        self.overrides.update(tables.pronunciations(source))
        taught = tables.names(source)
        self.names.update(taught)
        self.user_names.update(taught)
        self.name_starts = {key[0] for key in self.names}
        self.name_length = max((len(key) for key in self.names), default=1)
        self._cache = {}

    def _entry(self, word, entry):
        kind, value = entry
        if kind == "phones":
            return tuple(value)
        return convert(word, value, self.aligner.align(word, value))

    def known(self, word):
        """Pronunciation from the override list, the exceptions or the dictionary."""
        if word in self.overrides:
            return self._entry(word, self.overrides[word])
        if word in self.exceptions:
            return self._entry(word, self.exceptions[word])
        text = self.lexicon.get(word)
        return from_text(text) if text is not None else None

    def ordinary(self, word):
        """Pronunciation of a dictionary word that may be half of a compound.
        CMUdict is full of surnames; a word that is also listed with a regular
        ending ("webs", "screens") is an ordinary one."""
        if len(word) < 3 or not any(word + ending in self.lexicon for ending in ("s", "es", "ed", "ing")):
            return None
        return self.known(word)

    def guess(self, word):
        """The unknown-word model, then the conversion rules, on one spelling."""
        if self.model is None:
            return self.spell(word)
        spelling = self.model.spellable(word)
        symbols = self.model.predict(spelling)
        # The model emits each phoneme on its own, and between two possible vowels before
        # an r it sometimes emits neither ("okafor" -> ... F R). An r with no vowel beside
        # it is a syllable: write it as one.
        for k, symbol in enumerate(symbols):
            if symbol == "R" and not any(0 <= j < len(symbols) and symbols[j][-1] in "012" for j in (k - 1, k + 1)):
                symbols[k] = "ER0"
        if not any(symbol[-1] in "012" for symbol in symbols):
            return self.spell(word)
        # Every word spoken alone has a main stress, even when the model marked none.
        return sentence.promote(convert(spelling, symbols, self.aligner.align(spelling, symbols)))

    def spell(self, letters):
        """Letter names, joined: the last letter carries the main stress."""
        global _LETTER_NAMES
        if _LETTER_NAMES is None:
            _LETTER_NAMES = {key: from_text(value) for key, value in tables.mapping("letters.txt").items()}
        possessive = letters.lower().endswith("'s")
        names = [_LETTER_NAMES[c] for c in (letters[:-2] if possessive else letters).lower() if c in _LETTER_NAMES]
        out = []
        for index, name in enumerate(names):
            out.extend((phone, 2 if stress and index < len(names) - 1 else stress) for phone, stress in name)
        return morphology.plural(tuple(out)) if possessive and out else tuple(out)

    def is_word(self, word):
        """True for a spelling the tables or the dictionary know."""
        return word in self.lexicon or word in self.functions or word in self.exceptions or word in self.overrides

    def from_parts(self, word):
        """``(phones, source)`` for two kinds of new word the model reads
        badly, or ``None``. A name in "-leigh" is said like the same name in
        "-ley" (Kayleigh, Ryleigh). A word in "-virus" is its first part, from
        the dictionary or the model, and then "virus" (coronavirus)."""
        if word.endswith("'s") and len(word) > 3:
            found = self.from_parts(word[:-2])
            return found and (morphology.plural(found[0]), found[1])
        if _LEIGH.search(word):
            return self.word(_LEIGH.sub("ley", word))
        for tail in _VIRUS:
            second = self.known(tail) if word.endswith(tail) and len(word) - len(tail) > 2 else None
            if second is not None:
                first, source = self.word(word[:-len(tail)])
                phones = sentence.promote(settle_stress(morphology.compound(first, second)))
                return phones, "model" if source == "model" else "ending"
        return None

    def word(self, word):
        """``(phones, source)`` for one spelling in lower case."""
        if word in self._cache:
            return self._cache[word]
        phones, source = self.known(word), "dictionary"
        if phones is None:
            phones, source = morphology.derive(word, self.known, self.ordinary), "ending"
            if phones is not None:
                phones = settle_stress(phones)
        if phones is None:
            found = self.from_parts(word)
            if found:
                phones, source = found
        if phones is None and word.endswith("'s") and len(word) > 3:
            phones, source = morphology.plural(self.guess(word[:-2])), "model"
        if phones is None:
            phones, source = self.guess(word), "model"
        self._cache[word] = (phones, source)
        return phones, source

    # ---- sentences ----------------------------------------------------

    def _units(self, words, places=None, written=None):
        """Units of one clause from its ``normalize.Word`` tokens. ``written``
        is the whole text as tokens and ``places`` where each word sits in it,
        for the homograph rules."""
        units, index = [], 0
        while index < len(words):
            token = words[index]
            if token.phones is not None:
                units.append(Unit(token.text, tuple(token.phones), "p", attach=token.attach, source="inline"))
            elif token.spell:
                units.append(Unit(token.text, self.spell(token.text), "p", attach=token.attach, source="letters"))
            else:
                size = self._name(words, index) if token.text in self.name_starts else 0
                if size:                                    # a taught name: every word as written in the table
                    key = tuple(w.text for w in words[index:index + size])
                    units.extend(Unit(text, self._entry(text, entry), "p", attach=token.attach and position == 0, source="name")
                                 for position, (text, entry) in enumerate(zip(key, self.names[key])))
                    index += size
                    continue
                size = self._phrase(words, index)
                if size:
                    key = tuple(w.text for w in words[index:index + size])
                    kind, forms, final = self.phrases[key]
                    if len(forms) == 1:
                        units.append(Unit(" ".join(key), forms[0], kind, final, token.attach, "phrase"))
                    else:                                   # the boundaries stay, only the stress is fixed
                        units.extend(Unit(text, form, kind, attach=token.attach and position == 0, source="phrase")
                                     for position, (text, form) in enumerate(zip(key, forms)))
                    index += size
                    continue
                if token.text in self.overrides:
                    units.append(Unit(token.text, self.known(token.text), "c", attach=token.attach, source="override"))
                elif self.homographs and written and self.homographs.covers(token.text) and token.text not in self.exceptions:
                    phones, ending = self.homographs.pronounce(token.text, written, places[index], token.attach)
                    phones = morphology.plural(from_text(phones)) if ending else from_text(phones)
                    units.append(Unit(token.text, phones, "c", attach=token.attach, source="homograph"))
                elif token.text in self.functions:
                    kind, form, final = self.functions[token.text]
                    units.append(Unit(token.text, form, kind, final, token.attach, "function"))
                else:
                    phones, source = self.word(token.text)
                    units.append(Unit(token.text, phones, "c", attach=token.attach, source=source))
            index += 1
        return units

    def _name(self, words, index):
        for size in range(min(self.name_length, len(words) - index), 1, -1):
            span = words[index:index + size]
            key = tuple(w.text for w in span)
            if key in self.names and all(w.phones is None and not w.spell for w in span) and not any(w.attach for w in span[1:]) \
                    and (key in self.user_names or not any(w.text in self.overrides for w in span)):
                return size                                 # the user's own word list wins over a built-in name
        return 0

    def _phrase(self, words, index):
        for size in range(min(self.phrase_length, len(words) - index), 1, -1):
            span = words[index:index + size]
            if all(w.phones is None and not w.spell and not w.attach for w in span[1:]) and span[0].phones is None \
                    and not span[0].spell and tuple(w.text for w in span) in self.phrases \
                    and not any(w.text in self.overrides for w in span):
                return size
        return 0

    def analyse(self, text):
        """Clauses and marks in order: ``("punct", mark)`` or ``("clause", [Unit, ...])``."""
        stream = self.normalizer.tokens(text)
        # The text as the homograph rules see it; a word given only as phones stands as "x".
        written = [token.mark if isinstance(token, normalize.Punct) else (token.raw or token.text or "x") for token in stream]
        out, words, places = [], [], []

        def flush():
            if words:
                units = self._units(words, places, written)
                sentence.stress_clause(units)
                sentence.join_clause(units)
                out.append(("clause", units))
                words.clear()
                places.clear()

        for place, token in enumerate(stream):
            if isinstance(token, normalize.Punct):
                flush()
                out.append(("punct", token.mark))
            else:
                words.append(token)
                places.append(place)
        flush()
        return out

    def pieces(self, text):
        """The structure ``symbols.tokenize`` takes: ``(True, mark)`` for
        punctuation, ``(False, [[(phone, stress), ...], ...])`` for a run of words."""
        return [(True, value) if kind == "punct" else (False, sentence.groups(value)) for kind, value in self.analyse(text)]
