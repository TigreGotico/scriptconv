"""Each ByT5 model reads the language prefix of its own training data.

The CharsiuG2P README (github.com/lingjzhu/CharsiuG2P) says: "Each word must
be proceeded by a language code prefix ... For example, the prefix code for
American English is '<eng-us>: ' (The space following the colon cannot be
omitted!)". Its examples feed ``'<eng-us>: ' + word`` and ``'<tha>: ภาษา'``
through the ByT5 tokenizer with ``add_special_tokens=False``. The ByT5
tokenizer maps byte ``b`` to id ``b + 3``.

The OpenVoiceOS ByT5 model uses the same ``<tag>: word`` form with its own
BCP-47 tags, as ``<pt-PT>: w``.
"""
import json
import os
import tempfile
import unittest
from unittest import mock

import numpy as np

from scriptconv.phonemizers.mul import ByT5Phonemizer, CharsiuPhonemizer


class _RecordingSession:
    """An ONNX session stand-in that records ``input_ids`` and emits EOS."""

    def __init__(self):
        self.input_ids = []

    def get_outputs(self):
        return [mock.Mock(name="logits")]

    def run(self, output_names, inputs):
        self.input_ids.append(inputs["input_ids"])
        logits = np.zeros((1, 1, 4), dtype=np.float32)
        logits[0, -1, 1] = 1.0  # id 1 is </s>
        return [logits]


class TestByT5LangPrefix(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.model = os.path.join(tmp.name, "model.onnx")
        self.tokenizer = os.path.join(tmp.name, "tokenizer_config.json")
        open(self.model, "wb").close()
        with open(self.tokenizer, "w") as f:
            json.dump({"added_tokens_decoder": {"0": {"content": "<pad>"},
                                                "1": {"content": "</s>"},
                                                "2": {"content": "<unk>"}}}, f)

    def model_input(self, cls, lang, word="w"):
        session = _RecordingSession()
        with mock.patch("scriptconv.phonemizers.mul.make_session", return_value=session):
            phonemizer = cls(model=self.model, tokenizer_config=self.tokenizer)
        phonemizer.phonemize_string(word, lang)
        (input_ids,) = session.input_ids
        return bytes(int(i) - 3 for i in input_ids[0])

    def assertPrefixes(self, cls, cases):
        for lang, expected in cases.items():
            with self.subTest(cls=cls.__name__, lang=lang):
                self.assertEqual(self.model_input(cls, lang), expected)

    def test_charsiu_reads_charsiu_labels(self):
        self.assertPrefixes(CharsiuPhonemizer, {
            "srp": "<srp>: w".encode(),
            "por-po": "<por-po>: w".encode(),
            "kur": "<kur>: w".encode(),
            "eng-us": "<eng-us>: w".encode(),
            "pt-PT": "<por-po>: w".encode(),
        })

    def test_charsiu_readme_example(self):
        self.assertEqual(self.model_input(CharsiuPhonemizer, "tha", "ภาษา"),
                         "<tha>: ภาษา".encode())

    def test_openvoiceos_byt5_reads_bcp47_tags(self):
        self.assertPrefixes(ByT5Phonemizer, {
            "pt-PT": "<pt-PT>: w".encode(),
            "sr-RS": "<sr-RS>: w".encode(),
            "en-US": "<en-US>: w".encode(),
            "zh-CN": "<zh-CN>: w".encode(),
        })


if __name__ == "__main__":
    unittest.main()
