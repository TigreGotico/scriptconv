"""The ghana-g2p wrapper ``GhanaG2PPhonemizer`` is in scriptconv-nonfree.

``pip install scriptconv[ghana]`` installs that package. Import the class from
``scriptconv_nonfree.phonemizers.ghana``, or construct it through
:func:`scriptconv.phonemizers.get_phonemizer`.
"""
from scriptconv.phonemizers._moved import deprecated_getattr

__getattr__ = deprecated_getattr(__name__)
