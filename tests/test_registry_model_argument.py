"""A model argument must reach the backend or raise.

get_phonemizer forwards ``model=`` to a constructor parameter named ``model``,
``engine`` or ``register``. A backend with none of those parameters cannot use
the value, so the call raises instead of falling back to a default model.
"""
import unittest
from unittest.mock import patch

import scriptconv.phonemizers.registry as registry
from scriptconv.phonemizers.enums import Alphabet, Phonemizer
from scriptconv.phonemizers.base import BasePhonemizer


class Recorder(BasePhonemizer):
    """A backend that records the constructor arguments it receives."""

    seen = {}

    def __init__(self, **kwargs):
        self.seen = dict(kwargs)
        super().__init__(kwargs.get("alphabet", Alphabet.IPA))

    def phonemize_string(self, text, lang):
        return text


class TestModelArgument(unittest.TestCase):
    def _build(self, cls, model):
        with patch.object(registry, "get_phonemizer_class", return_value=cls):
            return registry.get_phonemizer(Phonemizer.G2PW, model=model)

    def test_a_model_parameter_receives_the_value(self):
        class Backend(Recorder):
            def __init__(self, model=None, alphabet=Alphabet.IPA):
                super().__init__(model=model, alphabet=alphabet)

        inst = self._build(Backend, "/tmp/weights.onnx")
        self.assertEqual(inst.seen["model"], "/tmp/weights.onnx")

    def test_an_engine_parameter_receives_the_value(self):
        class Backend(Recorder):
            def __init__(self, engine=None, alphabet=Alphabet.IPA):
                super().__init__(engine=engine, alphabet=alphabet)

        inst = self._build(Backend, "classic")
        self.assertEqual(inst.seen["engine"], "classic")

    def test_a_register_parameter_receives_the_value(self):
        class Backend(Recorder):
            def __init__(self, register=None, alphabet=Alphabet.IPA):
                super().__init__(register=register, alphabet=alphabet)

        inst = self._build(Backend, "mini")
        self.assertEqual(inst.seen["register"], "mini")

    def test_a_backend_with_no_slot_raises_and_names_it(self):
        class Backend(Recorder):
            def __init__(self, alphabet=Alphabet.IPA):
                super().__init__(alphabet=alphabet)

        with patch.object(registry, "get_phonemizer_class", return_value=Backend):
            with self.assertRaises(ValueError) as ctx:
                registry.get_phonemizer(Phonemizer.G2PW, model="/tmp/weights.onnx")
        message = str(ctx.exception)
        self.assertIn("g2pw", message)
        self.assertIn("Backend", message)
        self.assertIn("model", message)

    def test_no_model_keeps_the_default(self):
        class Backend(Recorder):
            def __init__(self, alphabet=Alphabet.IPA):
                super().__init__(alphabet=alphabet)

        inst = self._build(Backend, None)
        self.assertEqual(inst.seen, {"alphabet": Alphabet.IPA})

    def test_an_empty_model_keeps_the_default(self):
        class Backend(Recorder):
            def __init__(self, alphabet=Alphabet.IPA):
                super().__init__(alphabet=alphabet)

        inst = self._build(Backend, "")
        self.assertEqual(inst.seen, {"alphabet": Alphabet.IPA})


if __name__ == "__main__":
    unittest.main()
