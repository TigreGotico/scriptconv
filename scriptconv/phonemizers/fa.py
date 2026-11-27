"""The Persian wrapper ``PersianPhonemizer`` is in scriptconv-copyleft.

``pip install scriptconv[fa]`` installs that package. Import the class from
``scriptconv_copyleft.phonemizers.fa``, or construct it through
:func:`scriptconv.phonemizers.get_phonemizer`.
"""
from scriptconv.phonemizers._moved import deprecated_getattr

__getattr__ = deprecated_getattr(__name__)
