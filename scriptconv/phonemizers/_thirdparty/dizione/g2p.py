"""The unknown-word model at run time: letters -> CMUdict phonemes.

Pure NumPy, one forward pass per word, no decoder loop. The network is the one
trained by ``scripts/train_g2p.py``: letter embeddings (each letter
given ``slots`` positions), residual convolutions, a bidirectional GRU and a
CTC output layer read greedily. The arithmetic below is the reference for the
portable implementation.
"""

import json
from pathlib import Path
import unicodedata

import numpy as np


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _layer_norm(x, weight, bias):
    mean = x.mean(axis=-1, keepdims=True)
    variance = ((x - mean) ** 2).mean(axis=-1, keepdims=True)
    return (x - mean) / np.sqrt(variance + 1e-5) * weight + bias


def _conv(x, weight, bias):
    """x: (frames, channels); weight: (out, in, kernel), zero padding."""
    kernel = weight.shape[2]
    pad = kernel // 2
    padded = np.pad(x, ((pad, pad), (0, 0)))
    out = np.zeros((x.shape[0], weight.shape[0]), dtype=np.float32) + bias
    for k in range(kernel):
        out += padded[k:k + x.shape[0]] @ weight[:, :, k].T
    return out


def _gru(x, w_ih, w_hh, b_ih, b_hh, reverse):
    size = w_hh.shape[1]
    inputs = x @ w_ih.T + b_ih
    state = np.zeros(size, dtype=np.float32)
    out = np.empty((x.shape[0], size), dtype=np.float32)
    for t in (range(x.shape[0] - 1, -1, -1) if reverse else range(x.shape[0])):
        recurrent = w_hh @ state + b_hh
        reset = _sigmoid(inputs[t, :size] + recurrent[:size])
        update = _sigmoid(inputs[t, size:2 * size] + recurrent[size:2 * size])
        candidate = np.tanh(inputs[t, 2 * size:] + reset * recurrent[2 * size:])
        state = (1.0 - update) * candidate + update * state
        out[t] = state
    return out


class Model:
    def __init__(self, directory):
        directory = Path(directory)
        self.settings = json.loads((directory / "g2p.json").read_text(encoding="utf-8"))
        with np.load(directory / "g2p.npz") as arrays:
            self.weights = {name: arrays[name] for name in arrays.files}
        self.letters = {letter: index + 1 for index, letter in enumerate(self.settings["letters"])}
        self.symbols = self.settings["symbols"]
        self.parameters = int(sum(value.size for value in self.weights.values()))

    def spellable(self, word):
        """The word reduced to the letters the model knows (accents removed)."""
        plain = unicodedata.normalize("NFKD", word.lower())
        return "".join(c for c in plain if c in self.letters).strip("'")

    def log_probabilities(self, word):
        w, slots = self.weights, self.settings["slots"]
        ids = [self.letters[c] for c in word]
        x = (w["embed__weight"][ids][:, None, :] + w["slot"][None, :, :]).reshape(len(ids) * slots, -1)
        for block in range(self.settings["convs"]):
            normed = _layer_norm(x, w[f"norms__{block}__weight"], w[f"norms__{block}__bias"])
            x = x + np.maximum(_conv(normed, w[f"convs__{block}__weight"], w[f"convs__{block}__bias"]), 0.0)
        for layer in range(self.settings["layers"]):
            both = []
            for suffix, reverse in (("", False), ("_reverse", True)):
                both.append(_gru(x, w[f"gru__weight_ih_l{layer}{suffix}"], w[f"gru__weight_hh_l{layer}{suffix}"],
                                 w[f"gru__bias_ih_l{layer}{suffix}"], w[f"gru__bias_hh_l{layer}{suffix}"], reverse))
            x = np.concatenate(both, axis=1)
        logits = x @ w["out__weight"].T + w["out__bias"]
        logits = logits - logits.max(axis=1, keepdims=True)
        return logits - np.log(np.exp(logits).sum(axis=1, keepdims=True))

    def predict(self, word):
        """CMUdict symbols with stress digits for ``word`` (letters and apostrophes)."""
        word = self.spellable(word)
        if not word:
            return []
        out, previous = [], 0
        for label in self.log_probabilities(word).argmax(axis=1):
            if label != previous and label != 0:
                out.append(self.symbols[label - 1])
            previous = label
        return out
