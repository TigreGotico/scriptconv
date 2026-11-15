"""Words spelled alike and pronounced differently: which reading is meant.

"I read it yesterday" / "to read", "a live show" / "they live here". For each
homograph of the Wikipedia Homograph Data a small linear classifier looks at
the neighbouring words. The weights are trained by
``scripts/train_homographs.py``; this module computes the same
features at run time and adds up the weights. No tagger, no network.

Two kinds of model:
  * noun-or-verb homographs (record, present, use, ...) share one set of
    weights on the grammatical class of the neighbours ("to" before, an
    article before, ...), so a verb reading is found even for a word whose
    verb sense never occurs in the training sentences; each word adds its own
    weights and prior;
  * the others (bass, bow, lead, read, ...) have weights of their own.
"""

import json
from pathlib import Path
import re

_CLASSES = (
    ("TO", "to"),
    ("DET", "the a an this that these those every each no some any another such what which whose"),
    ("POSS", "my your his her its our their"),
    ("SUBJ", "i you he she it we they who"),
    ("OBJ", "me him us them"),
    ("MODAL", "will would shall should can could may might must 'll 'd won't can't cannot couldn't shouldn't wouldn't let's please"),
    ("DO", "do does did don't doesn't didn't"),
    ("BE", "am is are was were be been being isn't aren't wasn't weren't i'm you're we're they're he's she's it's that's there's"),
    ("HAVE", "have has had having haven't hasn't hadn't i've you've we've they've"),
    ("NEG", "not never"),
    ("PREP", "of in on at by for from with into onto over under about after before between through during without within "
             "against among around across behind beside near upon toward towards as than like"),
    ("CONJ", "and or but nor so yet if because although though while when where unless until since whether"),
    ("ADV", "very too quite rather more most less least also just only even still always often sometimes usually again "
            "now then here there soon already almost"),
)
_TAG = {word: name for name, words in _CLASSES for word in words.split()}
TOKEN = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)*|\d+(?:[.,]\d+)*|\S")
SENTENCE_END = frozenset((".", "?", "!"))
WINDOW = 6


def tag(token):
    """Coarse grammatical class of a neighbouring token, from closed lists and endings."""
    if token in ("<s>", "</s>"):
        return token
    if not token[0].isalpha():
        return "NUM" if token[0].isdigit() else "PUNCT"
    lower = token.lower()
    if lower in _TAG:
        return _TAG[lower]
    for ending, name in (("'s", "POS"), ("ly", "LY"), ("ing", "ING"), ("ed", "ED")):
        if lower.endswith(ending) and len(lower) > len(ending) + 1:
            return name
    if lower.endswith("s") and not lower.endswith("ss") and len(lower) > 3:
        return "S"
    return "CAP" if token[0].isupper() else "W"


def features(tokens, index):
    """Names of the features that are on for ``tokens[index]``. ``tokens`` is
    one sentence: words as written, punctuation marks as their own tokens."""
    def at(offset):
        position = index + offset
        return tokens[position] if 0 <= position < len(tokens) else ("<s>" if offset < 0 else "</s>")

    p2, p1, n1, n2 = at(-2), at(-1), at(1), at(2)
    tp2, tp1, tn1, tn2 = tag(p2), tag(p1), tag(n1), tag(n2)
    out = ["tp1=" + tp1, "tp2=" + tp2, "tn1=" + tn1, "tn2=" + tn2, "tp2p1=" + tp2 + "+" + tp1, "tp1n1=" + tp1 + "+" + tn1,
           "tn1n2=" + tn1 + "+" + tn2]
    if index == 0:
        out.append("first")
    elif tokens[index][0].isupper():
        out.append("cap")
    out += ["p1=" + p1.lower(), "p2=" + p2.lower(), "n1=" + n1.lower(), "n2=" + n2.lower()]
    target = tokens[index].lower()
    nearby = {t.lower() for t in tokens[max(0, index - WINDOW):index + WINDOW + 1] if t[0].isalpha()} - {target}
    out += ["w=" + word for word in sorted(nearby)]
    return out


def shared(names):
    """The features of the noun-or-verb model that all its words share."""
    return [name for name in names if name[0] == "t" or name in ("first", "cap")]


def sentence_of(tokens, index):
    """The sentence around ``tokens[index]`` and the index inside it."""
    start = index
    while start > 0 and tokens[start - 1] not in SENTENCE_END:
        start -= 1
    end = index
    while end < len(tokens) and tokens[end] not in SENTENCE_END:
        end += 1
    return tokens[start:end + 1], index - start


_SKIP_FOR_BEFORE = frozenset(("ADV", "NEG", "LY"))
_SKIP_FOR_AUX = _SKIP_FOR_BEFORE | frozenset(("SUBJ", "OBJ", "DET", "POSS"))


def _left(tokens, index, skip):
    """The nearest token to the left that is not of a skipped class, in lower
    case, with "'ll" and "'ve" read as "will" and "have"."""
    for position in range(index - 1, max(index - 6, -1), -1):
        token = tokens[position]
        if tag(token) in skip:
            continue
        lower = token.lower()
        return "will" if lower.endswith("'ll") else "have" if lower.endswith("'ve") else lower
    return "<s>"


def read_rules(source="homograph_rules.txt"):
    """word -> [(sense id, [(condition, words)])] from the hand-written table."""
    from .tables import rows
    rules = {}
    for number, columns in rows(source):
        if len(columns) != 3:
            raise ValueError(f"homograph_rules.txt line {number}: expected word, sense, conditions")
        conditions = []
        for part in columns[2].split(";"):
            name, _, words = part.strip().partition(":")
            if name not in ("aux", "before", "next", "near", "first", "joined") or (name == "first") == bool(words.strip()):
                raise ValueError(f"homograph_rules.txt line {number}: bad condition {part.strip()!r}")
            conditions.append((name, frozenset(words.split())))
        rules.setdefault(columns[0], []).append((columns[1], conditions))
    return rules


def _holds(condition, words, tokens, index, joined=False):
    if condition == "first":
        return index == 0
    if condition == "joined":
        return joined and index > 0 and tokens[index - 1].lower() in words
    if condition == "aux":
        return _left(tokens, index, _SKIP_FOR_AUX) in words
    if condition == "before":
        return _left(tokens, index, _SKIP_FOR_BEFORE) in words
    if condition == "next":
        return (tokens[index + 1].lower() if index + 1 < len(tokens) else "</s>") in words
    return any(token.lower() in words for token in tokens[max(0, index - WINDOW):index + WINDOW + 1])


class Homographs:
    def __init__(self, path, rules=None):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.words = data["words"]                 # word -> {"senses": [{"id", "role", "phones"}], "model": ...}
        self.pooled = data["pooled"]               # {"bias": b, "weights": {feature: w}} for the verb reading
        self.plural_bases = frozenset(data.get("plural_bases", ()))
        self.rules = read_rules() if rules is None else rules
        for word, word_rules in self.rules.items():
            known = {sense["id"] for sense in self.words[word]["senses"]} if word in self.words else set()
            for sense, _ in word_rules:
                if sense not in known:
                    raise ValueError(f"homograph rule for {word!r} names the unknown sense {sense!r}")

    def __contains__(self, word):
        return word in self.words

    def covers(self, word):
        """True for a homograph and for the regular -s form of a noun-or-verb one."""
        return word in self.words or (word.endswith("s") and word[:-1] in self.plural_bases)

    def pronounce(self, word, tokens, index, joined=False):
        """``(phones as text, needs the -s ending)`` for ``tokens[index]``.
        ``joined`` says a hyphen joins the word to the one before it."""
        if word in self.words:
            return self.choose(word, tokens, index, joined)["phones"], False
        entry = self.words[word[:-1]]
        adjective = next((sense for sense in entry["senses"] if sense["role"] == "n"), None)
        if adjective and adjective["id"] == "adj":                 # "separates" can only be the verb
            return next(sense for sense in entry["senses"] if sense["role"] == "v")["phones"], True
        return self.choose(word[:-1], tokens, index, joined)["phones"], True

    def scores(self, word, tokens, index):
        """Score of every sense of ``word`` (higher is more likely)."""
        entry = self.words[word]
        names = features(*sentence_of(tokens, index))
        model = entry["model"]
        if model["kind"] == "noun-verb":
            verb = self.pooled["bias"] + sum(self.pooled["weights"].get(name, 0.0) for name in shared(names))
            verb += model["bias"] + sum(model["weights"].get(name, 0.0) for name in names)
            return [verb if sense["role"] == "v" else -verb for sense in entry["senses"]]
        return [bias + sum(weights.get(name, 0.0) for name in names) for bias, weights in zip(model["bias"], model["weights"])]

    def choose(self, word, tokens, index, joined=False):
        """The sense meant by ``tokens[index]``: ``{"id", "role", "phones"}``.
        Hand rules first, then the classifier."""
        entry = self.words[word]
        sentence, position = sentence_of(tokens, index)
        for sense, conditions in self.rules.get(word, ()):
            if all(_holds(name, words, sentence, position, joined) for name, words in conditions):
                return next(s for s in entry["senses"] if s["id"] == sense)
        scores = self.scores(word, tokens, index)
        return entry["senses"][max(range(len(scores)), key=scores.__getitem__)]
