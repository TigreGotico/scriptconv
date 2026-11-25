"""A model value is never silently dropped by the phonemizer registry.

Only a constructor that declares ``model``, ``engine`` or ``register`` can take
*model*. The three positional-model backends keep their existing call.
"""
from unittest import mock

import pytest

from scriptconv.phonemizers import Alphabet
from scriptconv.phonemizers.enums import Phonemizer
import scriptconv.phonemizers.registry as reg

MODEL = "/path/to/model.onnx"


class Bare:
    def __init__(self, alphabet=Alphabet.IPA):
        self.alphabet = alphabet


class WithModel(Bare):
    def __init__(self, model=None, alphabet=Alphabet.IPA):
        self.model = model
        super().__init__(alphabet)


class WithEngine(Bare):
    def __init__(self, engine=None, alphabet=Alphabet.IPA):
        self.engine = engine
        super().__init__(alphabet)


class WithRegister(Bare):
    def __init__(self, register=None, alphabet=Alphabet.IPA):
        self.register = register
        super().__init__(alphabet)


class WithKwargs(Bare):
    def __init__(self, alphabet=Alphabet.IPA, **kwargs):
        self.kwargs = kwargs
        super().__init__(alphabet)


class Positional:
    def __init__(self, model, **kwargs):
        self.model = model


def test_a_backend_without_a_model_parameter_rejects_the_path():
    with mock.patch.object(reg, "get_phonemizer_class", return_value=Bare):
        with pytest.raises(ValueError, match="cannot take model=") as exc:
            reg.get_phonemizer(Phonemizer.G2PW, model=MODEL)
    assert Phonemizer.G2PW.value in str(exc.value)
    assert MODEL in str(exc.value)
    assert "Bare" in str(exc.value)


def test_arbitrary_keywords_do_not_count_as_a_model_parameter():
    with mock.patch.object(reg, "get_phonemizer_class", return_value=WithKwargs):
        with pytest.raises(ValueError, match="cannot take model="):
            reg.get_phonemizer(Phonemizer.G2PW, model=MODEL)


def test_model_none_is_not_a_request_for_another_model():
    with mock.patch.object(reg, "get_phonemizer_class", return_value=Bare):
        assert isinstance(reg.get_phonemizer(Phonemizer.G2PW, model=None), Bare)


def test_an_empty_model_is_not_a_request_for_another_model():
    with mock.patch.object(reg, "get_phonemizer_class", return_value=Bare):
        assert isinstance(reg.get_phonemizer(Phonemizer.G2PW, model=""), Bare)


@pytest.mark.parametrize("cls,name", [(WithModel, "model"), (WithEngine, "engine"),
                                      (WithRegister, "register")])
def test_declared_model_parameters_still_receive_the_path(cls, name):
    with mock.patch.object(reg, "get_phonemizer_class", return_value=cls):
        inst = reg.get_phonemizer(Phonemizer.AHOTTS, model=MODEL)
    assert getattr(inst, name) == MODEL


def test_positional_model_backends_still_receive_the_path():
    with mock.patch.object(reg, "get_phonemizer_class", return_value=Positional):
        inst = reg.get_phonemizer(Phonemizer.BYT5, model=MODEL)
    assert inst.model == MODEL


def test_language_defaults_reject_an_unused_override_model():
    with mock.patch.object(reg, "get_phonemizer_class", return_value=Bare):
        with pytest.raises(ValueError, match="cannot take model="):
            reg.phonemizer_for_lang("en", override=Phonemizer.G2PW, model=MODEL)
