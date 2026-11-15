"""The Galician wrapper ``CotoviaPhonemizer`` is in scriptconv-copyleft.

``pip install scriptconv[gl]`` installs that package. Import the class from
``scriptconv_copyleft.phonemizers.gl``, or construct it through
:func:`scriptconv.phonemizers.get_phonemizer`.
"""
from scriptconv.phonemizers._moved import deprecated_getattr

__getattr__ = deprecated_getattr(__name__)
