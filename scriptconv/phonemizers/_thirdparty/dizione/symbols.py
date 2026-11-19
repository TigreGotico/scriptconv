"""The phone inventory and the token sequence built from it.

59 phones of American English, 12 punctuation marks and 5 special tokens. Lexical stress is a parallel feature (0 none, 1 primary,
2 secondary), not a symbol. The order is append-only: models trained on these
ids depend on it.
"""

from dataclasses import dataclass

PAD, BOS, EOS, SP, UNK = "<pad>", "<bos>", "<eos>", "<sp>", "<unk>"
SPECIALS = (PAD, BOS, EOS, SP, UNK)
PUNCTUATION = (",", ".", "?", "!", ";", ":", '"', "'", "(", ")", "—", "…")
CONSONANTS = ("p", "b", "t", "d", "k", "ɡ", "f", "v", "θ", "ð", "s", "z", "ʃ", "ʒ", "h",
              "m", "n", "ŋ", "l", "ɹ", "j", "w", "tʃ", "dʒ", "ɾ", "ʔ")
VOWELS = ("ə", "ɐ", "ɚ", "ᵻ", "ɪ", "i", "iː", "ɛ", "æ", "ʌ", "ɑː", "ɔ", "ɔː", "ʊ", "uː", "ɜː",
          "eɪ", "aɪ", "ɔɪ", "oʊ", "aʊ", "iə", "oː",
          "ɑːɹ", "ɔːɹ", "oːɹ", "ɪɹ", "ɛɹ", "ʊɹ", "aɪɚ", "aɪə", "əl", "n̩")
PHONES = CONSONANTS + VOWELS
SYMBOLS = SPECIALS + PUNCTUATION + PHONES
SYMBOL_TO_ID = {symbol: index for index, symbol in enumerate(SYMBOLS)}
PHONE_SET = frozenset(PHONES)
VOWEL_SET = frozenset(VOWELS)
STRESS_MARKS = {1: "ˈ", 2: "ˌ"}


@dataclass(frozen=True)
class Phonemized:
    symbols: tuple
    ids: tuple
    stress: tuple
    unknown: tuple  # phones outside the inventory (never produced by the built-in rules)

    def __len__(self):
        return len(self.ids)

    def __str__(self):
        return " ".join(STRESS_MARKS.get(level, "") + symbol for symbol, level in zip(self.symbols, self.stress))


def tokenize(pieces):
    """Build the token sequence from ``(is_punctuation, value)`` pieces, where
    a text piece's value is a list of words and a word is a list of
    ``(phone, stress)``. Words are separated by ``<sp>``; repeated punctuation
    is collapsed."""
    symbols, stress, unknown = [BOS], [0], []
    for punctuation, value in pieces:
        if punctuation:
            if symbols[-1] != value:
                symbols.append(value)
                stress.append(0)
            continue
        for word in value:
            if symbols[-1] in PHONE_SET or symbols[-1] == UNK:
                symbols.append(SP)
                stress.append(0)
            for phone, level in word:
                if phone in PHONE_SET:
                    symbols.append(phone)
                    stress.append(level)
                else:
                    unknown.append(phone)
                    symbols.append(UNK)
                    stress.append(0)
    symbols.append(EOS)
    stress.append(0)
    if not any(s in PHONE_SET or s == UNK for s in symbols):
        raise ValueError("the text has nothing to pronounce")
    return Phonemized(tuple(symbols), tuple(SYMBOL_TO_ID[s] for s in symbols), tuple(stress), tuple(unknown))
