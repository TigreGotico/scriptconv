"""Unified IPA phoneme inventory for Levantine-Arabic / English code-switching TTS.

Ported from hams_tts.text.phoneme_inventory (Apache-2.0) of Al-aminI/hams-levantine-tts.
The inventories, language IDs and tokenisation logic are identical to upstream, so
exported ShamiVITS checkpoints remain compatible. Two inventories exist:

* 88 symbols, as at upstream commit d7a3602 (the single-speaker models).  The
  module-level ``SYMBOL_TO_ID``, ``VOCAB_SIZE``, ``tokenize_ipa`` and ``encode`` use it.
* 90 symbols, as at upstream commit 80d79d0 (the multi-speaker models): the 88 plus
  ``sil`` (id 88) and ``brk`` (id 89), and the espeak reduced vowel ``ᵻ`` folded to ``ə``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Dict, List, Tuple


class Lang(IntEnum):
    """Language-ID stream values (fed to the model as an embedding index)."""

    PAD = 0
    AR = 1  # Levantine Arabic
    EN = 2  # English
    NEUTRAL = 3  # punctuation, silence, boundaries, digits handled upstream


# --------------------------------------------------------------------------------------
# Special / structural symbols
# --------------------------------------------------------------------------------------
PAD = "<pad>"
BOS = "<bos>"
EOS = "<eos>"
UNK = "<unk>"
WORD_SEP = " "  # white space = word boundary (kept, it conditions prosody)
SYL_SEP = "."  # syllable boundary (optional, emitted by syllabifier)
# Punctuation that the acoustic model is allowed to "see" (drives pausing/prosody).
PUNCT = [",", ".", "?", "!", ";", ":", "…", "—", "(", ")", '"', "«", "»"]

SPECIALS = [PAD, BOS, EOS, UNK, WORD_SEP, SYL_SEP]

# --------------------------------------------------------------------------------------
# Suprasegmentals (order-independent, but must be in the inventory to be tokenisable)
# --------------------------------------------------------------------------------------
SUPRASEGMENTALS = [
    "ˈ",  # primary stress (U+02C8)
    "ˌ",  # secondary stress (U+02CC)
    "ː",  # length mark (U+02D0)
]

# --------------------------------------------------------------------------------------
# Consonants -- union of the Levantine-Arabic and English inventories, in IPA.
# Multi-codepoint symbols (tie bars, pharyngealisation) are listed explicitly so the
# longest-match tokeniser can find them.
# --------------------------------------------------------------------------------------
CONSONANTS = [
    # --- shared / English-leaning ---
    "p", "b", "t", "d", "k", "ɡ",          # plosives
    "t͡ʃ", "d͡ʒ",                            # affricates
    "f", "v", "θ", "ð", "s", "z",          # fricatives
    "ʃ", "ʒ", "h", "x", "ɣ",               # more fricatives
    "m", "n", "ŋ",                          # nasals
    "l", "ɫ",                               # laterals
    "r", "ɾ", "ɹ",                          # rhotics
    "w", "j",                               # glides
    # --- Arabic-specific (Levantine) ---
    "ʔ",   # glottal stop
    "q",   # uvular plosive
    "ħ",   # voiceless pharyngeal fricative
    "ʕ",   # voiced pharyngeal fricative
    "sˤ",  # emphatic s
    "dˤ",  # emphatic d
    "tˤ",  # emphatic t
    "ðˤ",  # emphatic interdental
    "zˤ",  # emphatic z
]

# --------------------------------------------------------------------------------------
# Vowels
# --------------------------------------------------------------------------------------
VOWELS = [
    # short
    "a", "i", "u", "e", "o", "ə",
    # English lax / extra qualities
    "ɪ", "ʊ", "ɛ", "æ", "ʌ", "ɑ", "ɒ", "ɔ", "ɜ", "ɐ",
    # long
    "aː", "iː", "uː", "eː", "oː", "ɑː", "ɔː", "ɜː",
    # diphthongs
    "a͡ɪ", "a͡ʊ", "e͡ɪ", "o͡ʊ", "ɔ͡ɪ",
]

# --------------------------------------------------------------------------------------
# Final ordered symbol table.  ORDER IS FROZEN: the model's embedding rows are indexed
# by this order.
# --------------------------------------------------------------------------------------
SYMBOLS: List[str] = (
    SPECIALS
    + PUNCT
    + SUPRASEGMENTALS
    + CONSONANTS
    + VOWELS
)

_seen: set = set()
_ordered: List[str] = []
for _s in SYMBOLS:
    if _s not in _seen:
        _seen.add(_s)
        _ordered.append(_s)
SYMBOLS = _ordered

FOLD_MAP: Dict[str, str] = {
    "g": "ɡ",
    "ɡ": "ɡ",
    "c": "k",
    "y": "j",
    "ʤ": "d͡ʒ",
    "ʧ": "t͡ʃ",
    "dʒ": "d͡ʒ",
    "tʃ": "t͡ʃ",
    "aɪ": "a͡ɪ",
    "aʊ": "a͡ʊ",
    "eɪ": "e͡ɪ",
    "oʊ": "o͡ʊ",
    "ɔɪ": "ɔ͡ɪ",
    "ɝ": "ɜː",
    "ɚ": "ə",
    "ɡ̃": "ŋ",
    "ʁ": "ɣ",
    "χ": "x",
    "ɹ̩": "ɹ",
    "ɫ̩": "ɫ",
    "ɐ": "ə",
}

# The 90-symbol inventory of hams-levantine-tts at 80d79d0: two pause symbols appended
# after the 88 (clause pause at , ; : and sentence pause at . ! … —), and the espeak
# reduced vowel folded to schwa instead of to <unk>.
SIL = "sil"
BRK = "brk"
SYMBOLS_90: List[str] = SYMBOLS + [SIL, BRK]
FOLD_MAP_90: Dict[str, str] = {**FOLD_MAP, "ᵻ": "ə"}


@dataclass
class TokenizedPhonemes:
    """Result of tokenising an IPA string against the inventory."""

    symbols: List[str]
    ids: List[int]

    def __len__(self) -> int:
        return len(self.ids)


class Inventory:
    """One symbol table: its ids, its fold map and the tokeniser that uses them."""

    def __init__(self, symbols: List[str], fold_map: Dict[str, str]) -> None:
        self.symbols = symbols
        self.fold_map = fold_map
        self.symbol_to_id: Dict[str, int] = {s: i for i, s in enumerate(symbols)}
        self.id_to_symbol: Dict[int, str] = {i: s for s, i in self.symbol_to_id.items()}
        self.size = len(symbols)
        self._multi_first = sorted(
            [s for s in symbols if s not in (PAD, BOS, EOS, UNK)],
            key=lambda s: (-len(s), s),
        )

    def fold(self, symbol: str) -> str:
        """Map an arbitrary symbol to the nearest in-inventory symbol (or UNK)."""
        if symbol in self.symbol_to_id:
            return symbol
        if symbol in self.fold_map:
            return self.fold_map[symbol]
        stripped = symbol.replace("͡", "").replace("ː", "")
        if stripped in self.symbol_to_id:
            return stripped
        if stripped in self.fold_map:
            return self.fold_map[stripped]
        return UNK

    def tokenize(self, ipa: str) -> TokenizedPhonemes:
        """Greedy longest-match tokenisation of an IPA string into inventory symbols."""
        out_symbols: List[str] = []
        i = 0
        n = len(ipa)
        while i < n:
            ch = ipa[i]
            if ch.isspace():
                if out_symbols and out_symbols[-1] != WORD_SEP:
                    out_symbols.append(WORD_SEP)
                i += 1
                continue
            matched = None
            for cand in self._multi_first:
                if cand and ipa.startswith(cand, i):
                    matched = cand
                    break
            if matched is not None:
                out_symbols.append(matched)
                i += len(matched)
            else:
                out_symbols.append(self.fold(ch))
                i += 1
        cleaned: List[str] = []
        for s in out_symbols:
            if s == WORD_SEP and (not cleaned or cleaned[-1] == WORD_SEP):
                continue
            cleaned.append(s)
        while cleaned and cleaned[-1] == WORD_SEP:
            cleaned.pop()
        ids = [self.symbol_to_id[s] for s in cleaned]
        return TokenizedPhonemes(symbols=cleaned, ids=ids)

    def encode(self, ipa: str, add_bos_eos: bool = True) -> Tuple[List[int], List[str]]:
        """Tokenise + (optionally) wrap with BOS/EOS."""
        symbols = self.tokenize(ipa).symbols
        if add_bos_eos:
            symbols = [BOS] + symbols + [EOS]
        ids = [self.symbol_to_id[s] for s in symbols]
        return ids, symbols

    def decode(self, ids: List[int]) -> str:
        """Inverse of :meth:`encode` for debugging."""
        out = []
        for i in ids:
            s = self.id_to_symbol.get(i, UNK)
            if s in (BOS, EOS, PAD):
                continue
            out.append(s)
        return "".join(out)


INVENTORY_88 = Inventory(SYMBOLS, FOLD_MAP)
INVENTORY_90 = Inventory(SYMBOLS_90, FOLD_MAP_90)
INVENTORIES: Dict[int, Inventory] = {88: INVENTORY_88, 90: INVENTORY_90}


def get_inventory(size: int) -> Inventory:
    """The inventory with *size* symbols: 88 (single speaker) or 90 (with pauses).

    Raises:
        ValueError: If *size* is not the int 88 or 90. ``88.0``, ``True`` and
            ``"88"`` are refused.
    """
    if type(size) is not int or size not in INVENTORIES:
        raise ValueError(
            f"no Shami inventory has {size!r} symbols; use the int 88 or 90"
        )
    return INVENTORIES[size]


SYMBOL_TO_ID = INVENTORY_88.symbol_to_id
ID_TO_SYMBOL = INVENTORY_88.id_to_symbol
VOCAB_SIZE = INVENTORY_88.size
SYMBOL_TO_ID_90 = INVENTORY_90.symbol_to_id
ID_TO_SYMBOL_90 = INVENTORY_90.id_to_symbol
VOCAB_SIZE_90 = INVENTORY_90.size

fold_to_inventory = INVENTORY_88.fold
tokenize_ipa = INVENTORY_88.tokenize
encode = INVENTORY_88.encode
decode = INVENTORY_88.decode
