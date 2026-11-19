"""The Vietnamese wrapper ``VIPhonemePhonemizer`` is in scriptconv-nonfree.

``pip install scriptconv[vi]`` installs that package. Import the class from
``scriptconv_nonfree.phonemizers.vi``, or construct it through
:func:`scriptconv.phonemizers.get_phonemizer`.
"""
from scriptconv.phonemizers._moved import deprecated_getattr

__getattr__ = deprecated_getattr(__name__)
