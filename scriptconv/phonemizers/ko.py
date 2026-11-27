"""The Korean wrappers ``G2PKPhonemizer`` and ``KoG2PPhonemizer`` are in scriptconv-copyleft.

``pip install scriptconv[ko]`` installs that package. Import them from
``scriptconv_copyleft.phonemizers.ko``, or construct them through
:func:`scriptconv.phonemizers.get_phonemizer`.
"""
from scriptconv.phonemizers._moved import deprecated_getattr

__getattr__ = deprecated_getattr(__name__)
