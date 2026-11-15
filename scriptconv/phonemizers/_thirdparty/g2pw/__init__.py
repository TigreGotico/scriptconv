"""Polyphone disambiguation for Mandarin with the g2pW ONNX model, without torch.

Adapted from g2pW, https://github.com/GitYCC/g2pW at commit
b9328ce8129c4717a70f16a2688542a0197541dd, by Yi-Chang Chen, Yu-Chuan Chang,
Yen-Cheng Chang and Yi-Ren Yeh, under the Apache License, Version 2.0 (the
``LICENSE`` file in this directory). The code comes from ``g2pw/api.py``
(``G2PWConverter``, ``predict``), ``g2pw/dataset.py`` (``TextDataset``,
``get_phoneme_labels``, ``get_char_phoneme_labels``) and ``g2pw/utils.py``
(``wordize_and_map``, ``tokenize_and_map``).

The changes from g2pW:

- numpy arrays replace the torch tensors and the ``DataLoader``. The batches
  hold the same rows in the same order, padded with zeros as
  ``pad_sequence`` pads them.
- A ``tokenizers.Tokenizer`` replaces the ``transformers.BertTokenizer``.
- The caller gives the ONNX session, the tokenizer and the model's character
  lists. Nothing downloads here.
- The training paths, the part-of-speech tags and the progress bar are left
  out. ``style`` is always pinyin and the simplified-to-traditional mapping
  is always on.

The three tables in this directory are the files of ``g2pw/`` at the same
commit, unchanged: ``char_bopomofo_dict.json``,
``bopomofo_to_pinyin_wo_tune_dict.json`` and
``bert-base-chinese_s2t_dict.txt``.
"""
import json
import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

LOG = logging.getLogger(__name__)

TABLES = Path(__file__).parent

# The model's settings, as g2pw.utils.default_config_dict gives them.
DEFAULT_CONFIG = {"window_size": 32, "batch_size": 256, "use_mask": True,
                  "use_char_phoneme": False}


def wordize_and_map(text: str):
    """Words of *text*: a run of ASCII letters and digits, or one other character.

    Spaces belong to no word. Returns the words, the word of each character
    and the character span of each word.
    """
    words: List[str] = []
    text_to_word: List[Optional[int]] = []
    word_to_text: List[Tuple[int, int]] = []
    while text:
        match_space = re.match(r"^ +", text)
        if match_space:
            text_to_word += [None] * len(match_space.group(0))
            text = text[len(match_space.group(0)):]
            continue
        match_en = re.match(r"^[a-zA-Z0-9]+", text)
        word = match_en.group(0) if match_en else text[0]
        start = len(text_to_word)
        word_to_text.append((start, start + len(word)))
        text_to_word += [len(words)] * len(word)
        words.append(word)
        text = text[len(word):]
    return words, text_to_word, word_to_text


def tokenize_and_map(tokenizer, text: str):
    """Word pieces of *text*, the piece of each character and the span of each piece."""
    words, text_to_word, word_to_text = wordize_and_map(text)
    tokens: List[str] = []
    token_to_text: List[Tuple[int, int]] = []
    for word, (word_start, word_end) in zip(words, word_to_text):
        word_tokens = [tokenizer.id_to_token(i)
                       for i in tokenizer.encode(word, add_special_tokens=False).ids]
        if not word_tokens or word_tokens == ["[UNK]"]:
            token_to_text.append((word_start, word_end))
            tokens.append("[UNK]")
            continue
        start = word_start
        for word_token in word_tokens:
            end = start + len(re.sub(r"^##", "", word_token))
            token_to_text.append((start, end))
            start = end
            tokens.append(word_token)
    text_to_token = text_to_word
    for i, (token_start, token_end) in enumerate(token_to_text):
        for position in range(token_start, token_end):
            text_to_token[position] = i
    return tokens, text_to_token, token_to_text


def get_phoneme_labels(polyphonic_chars: Sequence[Sequence[str]]):
    """The sorted readings, and the label ids of each polyphonic character."""
    labels = sorted({phoneme for _, phoneme in polyphonic_chars})
    char2phonemes: Dict[str, List[int]] = {}
    for char, phoneme in polyphonic_chars:
        char2phonemes.setdefault(char, []).append(labels.index(phoneme))
    return labels, char2phonemes


def get_char_phoneme_labels(polyphonic_chars: Sequence[Sequence[str]]):
    """The sorted ``"<char> <reading>"`` labels, and the label ids of each character."""
    labels = sorted({f"{char} {phoneme}" for char, phoneme in polyphonic_chars})
    char2phonemes: Dict[str, List[int]] = {}
    for char, phoneme in polyphonic_chars:
        char2phonemes.setdefault(char, []).append(labels.index(f"{char} {phoneme}"))
    return labels, char2phonemes


def _truncate(max_len: int, text: str, query_id: int, tokens, text_to_token, token_to_text):
    """Keep at most ``max_len - 2`` pieces, centred on the queried character."""
    truncate_len = max_len - 2
    if len(tokens) <= truncate_len:
        return text, query_id, tokens, text_to_token, token_to_text
    token_start = text_to_token[query_id] - truncate_len // 2
    token_end = token_start + truncate_len
    front_exceed = -token_start
    back_exceed = token_end - len(tokens)
    if front_exceed > 0:
        token_start += front_exceed
        token_end += front_exceed
    elif back_exceed > 0:
        token_start -= back_exceed
        token_end -= back_exceed
    start = token_to_text[token_start][0]
    end = token_to_text[token_end - 1][1]
    return (text[start:end], query_id - start, tokens[token_start:token_end],
            [i - token_start if i is not None else None for i in text_to_token[start:end]],
            [(s - start, e - start) for s, e in token_to_text[token_start:token_end]])


def _pad(rows: List[List[int]]) -> np.ndarray:
    """*rows* padded at the end with zeros to the longest row, as int64."""
    out = np.zeros((len(rows), max(len(row) for row in rows)), dtype=np.int64)
    for i, row in enumerate(rows):
        out[i, :len(row)] = row
    return out


class _Untokenizable(Exception):
    """The pieces of a text do not cover its characters."""


class G2PWConverter:
    """Pinyin with a tone digit for each character that has a reading.

    Args:
        session: an ``onnxruntime.InferenceSession`` of ``g2pw.onnx``.
        tokenizer: the tokenizer of bert-base-chinese, a ``tokenizers.Tokenizer``
            or, from tokenizers 1.0, the ``CompiledTokenizer`` it compiles to.
        polyphonic: the lines of ``POLYPHONIC_CHARS.txt``, as ``(char, reading)``.
        monophonic: the lines of ``MONOPHONIC_CHARS.txt``, as ``(char, reading)``.
        config: the model's settings; missing keys take :data:`DEFAULT_CONFIG`.
    """

    def __init__(self, session, tokenizer, polyphonic: Sequence[Sequence[str]],
                 monophonic: Sequence[Sequence[str]], config: Optional[dict] = None):
        self.session = session
        self.tokenizer = tokenizer
        self.config = {**DEFAULT_CONFIG, **(config or {})}
        label_func = (get_char_phoneme_labels if self.config["use_char_phoneme"]
                      else get_phoneme_labels)
        self.labels, self.char2phonemes = label_func(polyphonic)
        self.chars = sorted(self.char2phonemes)
        self.monophonic = dict(monophonic)
        self.bopomofo_to_pinyin = json.loads(
            (TABLES / "bopomofo_to_pinyin_wo_tune_dict.json").read_text(encoding="utf-8"))
        self.char_bopomofo = json.loads(
            (TABLES / "char_bopomofo_dict.json").read_text(encoding="utf-8"))
        self.s2t = dict(line.split("\t") for line in (TABLES / "bert-base-chinese_s2t_dict.txt")
                        .read_text(encoding="utf-8").strip().split("\n"))

    def _to_pinyin(self, bopomofo: str) -> Optional[str]:
        """The pinyin of one bopomofo syllable that ends in its tone digit."""
        tone = bopomofo[-1]
        assert tone in "12345"
        component = self.bopomofo_to_pinyin.get(bopomofo[:-1])
        if component:
            return component + tone
        LOG.warning("cannot convert bopomofo %r to pinyin", bopomofo)
        return None

    def _features(self, text: str, query_id: int) -> dict:
        """The model inputs that ask for the reading of ``text[query_id]``."""
        window = self.config["window_size"]
        if window:
            start = max(0, query_id - window // 2)
            text = text[start:min(len(text), query_id + window // 2)]
            query_id -= start
        text = text.lower()
        try:
            tokens, text_to_token, token_to_text = tokenize_and_map(self.tokenizer, text)
        except Exception as e:
            raise _Untokenizable(text) from e
        text, query_id, tokens, text_to_token, token_to_text = _truncate(
            512, text, query_id, tokens, text_to_token, token_to_text)
        pieces = ["[CLS]"] + tokens + ["[SEP]"]
        query_char = text[query_id]
        candidates = self.char2phonemes[query_char]
        return {
            "input_ids": [self.tokenizer.token_to_id(piece) for piece in pieces],
            "phoneme_mask": [1 if i in candidates or not self.config["use_mask"] else 0
                             for i in range(len(self.labels))],
            "char_id": self.chars.index(query_char),
            # [CLS] is the first piece
            "position_id": text_to_token[query_id] + 1,
        }

    def _rows(self, texts: List[str], query_ids: List[int]) -> List[dict]:
        """The features of each query. A query whose text cannot be tokenized
        takes the features of the next query, as g2pW's ``TextDataset`` does."""
        rows = []
        for index in range(len(texts)):
            for offset in range(len(texts)):
                other = (index + offset) % len(texts)
                try:
                    rows.append(self._features(texts[other], query_ids[other]))
                    break
                except _Untokenizable as e:
                    LOG.warning("g2pW skips the text %r", e.args[0])
            else:
                raise ValueError("g2pW could not tokenize any text of the batch")
        return rows

    def _predict(self, rows: List[dict]) -> List[str]:
        preds: List[str] = []
        for start in range(0, len(rows), self.config["batch_size"]):
            batch = rows[start:start + self.config["batch_size"]]
            ids = _pad([row["input_ids"] for row in batch])
            probs = self.session.run([], {
                "input_ids": ids,
                "token_type_ids": np.zeros_like(ids),
                "attention_mask": _pad([[1] * len(row["input_ids"]) for row in batch]),
                "phoneme_mask": np.asarray([row["phoneme_mask"] for row in batch], dtype=np.float32),
                "char_ids": np.asarray([row["char_id"] for row in batch], dtype=np.int64),
                "position_ids": np.asarray([row["position_id"] for row in batch], dtype=np.int64),
            })[0]
            preds += [self.labels[pred] for pred in np.argmax(probs, axis=-1).tolist()]
        if self.config["use_char_phoneme"]:
            preds = [pred.split(" ")[1] for pred in preds]
        return preds

    def __call__(self, sentences) -> List[List[Optional[str]]]:
        """The pinyin of each character of each sentence, or ``None`` for a character with no reading."""
        if isinstance(sentences, str):
            sentences = [sentences]
        sentences = ["".join(self.s2t.get(char, char) for char in sentence) for sentence in sentences]
        texts: List[str] = []
        query_ids: List[int] = []
        sent_ids: List[int] = []
        results: List[List[Optional[str]]] = []
        for sent_id, sentence in enumerate(sentences):
            result: List[Optional[str]] = [None] * len(sentence)
            for i, char in enumerate(sentence):
                if char in self.char2phonemes:
                    texts.append(sentence)
                    query_ids.append(i)
                    sent_ids.append(sent_id)
                elif char in self.monophonic:
                    result[i] = self._to_pinyin(self.monophonic[char])
                elif char in self.char_bopomofo:
                    result[i] = self._to_pinyin(self.char_bopomofo[char][0])
            results.append(result)
        if texts:
            for sent_id, query_id, pred in zip(sent_ids, query_ids,
                                                self._predict(self._rows(texts, query_ids))):
                results[sent_id][query_id] = self._to_pinyin(pred)
        return results
