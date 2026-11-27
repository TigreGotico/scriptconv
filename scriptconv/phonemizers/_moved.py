"""Phonemizer wrappers that live in scriptconv-copyleft and scriptconv-nonfree.

The code of these wrappers, or a dependency of their engine, is under a
copyleft or a non-commercial licence, so the Apache-2.0 scriptconv wheel does
not hold them. The registry imports each one from its sister package, and the
scriptconv extra that served the wrapper installs that package.

The old import paths in scriptconv give the same classes until
:data:`REMOVAL_VERSION`, with a :class:`DeprecationWarning` on first use.
"""
import importlib
import sys
import warnings
from typing import Callable, Dict, Tuple

from scriptconv.version import VERSION_MAJOR, VERSION_MINOR

#: The scriptconv release that removes the old import paths.
REMOVAL_VERSION = f"{VERSION_MAJOR}.{VERSION_MINOR + 1}.0"

COPYLEFT = "scriptconv_copyleft.phonemizers"
NONFREE = "scriptconv_nonfree.phonemizers"

_MUL = f"{COPYLEFT}.mul"

#: old module -> moved name -> (new module, the scriptconv extra that installs it)
MOVED: Dict[str, Dict[str, Tuple[str, str]]] = {
    "scriptconv.phonemizers.mul": {
        "EspeakPhonemizer": (_MUL, "espeak"),
        "EspeakError": (_MUL, "espeak"),
        "TransphonePhonemizer": (_MUL, "transphone"),
        "MisakiPhonemizer": (_MUL, "misaki"),
        "MisakiEnPhonemizer": (_MUL, "misaki"),
        "MisakiJaPhonemizer": (_MUL, "misaki"),
        "MisakiZhPhonemizer": (_MUL, "misaki"),
        "MisakiKoPhonemizer": (_MUL, "misaki"),
        "MisakiViPhonemizer": (_MUL, "misaki"),
    },
    "scriptconv.phonemizers.gl": {"CotoviaPhonemizer": (f"{COPYLEFT}.gl", "gl")},
    "scriptconv.phonemizers.eu": {"AhoTTSPhonemizer": (f"{COPYLEFT}.eu", "eu")},
    "scriptconv.phonemizers.fa": {"PersianPhonemizer": (f"{COPYLEFT}.fa", "fa")},
    "scriptconv.phonemizers.ja": {"PyKakasiPhonemizer": (f"{COPYLEFT}.ja", "ja-phonemizers")},
    "scriptconv.phonemizers.ko": {
        "G2PKPhonemizer": (f"{COPYLEFT}.ko", "ko"),
        "KoG2PPhonemizer": (f"{COPYLEFT}.ko", "ko"),
    },
    "scriptconv.phonemizers.ar": {
        "MantoqPhonemizer": (f"{NONFREE}.ar", "ar-phonemizers"),
        "HalabiPhonemizer": (f"{NONFREE}.ar", "ar-phonemizers"),
        "IqraPhonemizer": (f"{NONFREE}.ar", "ar-phonemizers"),
    },
    "scriptconv.phonemizers.vi": {"VIPhonemePhonemizer": (f"{NONFREE}.vi", "vi")},
    "scriptconv.phonemizers.africa": {"AfricaG2PPhonemizer": (f"{NONFREE}.africa", "africa")},
    "scriptconv.phonemizers.ghana": {"GhanaG2PPhonemizer": (f"{NONFREE}.ghana", "ghana")},
}

#: old module -> old name -> new name in the same module
RENAMED: Dict[str, Dict[str, str]] = {
    "scriptconv.phonemizers.ja": {"OpenJTaklPhonemizer": "OpenJTalkPhonemizer"},
}


def import_moved(module: str, name: str, extra: str):
    """Return *name* from the sister *module*.

    Raises:
        ImportError: If the sister package is not installed. The message names
            the scriptconv extra that installs it.
    """
    try:
        return getattr(importlib.import_module(module), name)
    except ImportError as e:
        package = module.partition(".")[0].replace("_", "-")
        raise ImportError(
            f"{name} is in {package} — install it with "
            f"`pip install scriptconv[{extra}]`") from e


def deprecated_getattr(old_module: str) -> Callable[[str], object]:
    """A module ``__getattr__`` that gives the moved names of *old_module*.

    The first use of a name warns and stores the class on *old_module*, so
    each name warns once.
    """
    moved = MOVED.get(old_module, {})
    renamed = RENAMED.get(old_module, {})

    def __getattr__(name: str):
        if name in renamed:
            new_name = renamed[name]
            warnings.warn(
                f"{old_module}.{name} is deprecated and will be removed in scriptconv "
                f"{REMOVAL_VERSION}; use {old_module}.{new_name}",
                DeprecationWarning, stacklevel=2)
            value = getattr(sys.modules[old_module], new_name)
            setattr(sys.modules[old_module], name, value)
            return value
        if name not in moved:
            raise AttributeError(f"module {old_module!r} has no attribute {name!r}")
        module, extra = moved[name]
        warnings.warn(
            f"{old_module}.{name} is deprecated and will be removed in scriptconv "
            f"{REMOVAL_VERSION}; import it from {module} "
            f"(`pip install scriptconv[{extra}]`)",
            DeprecationWarning, stacklevel=2)
        value = import_moved(module, name, extra)
        setattr(sys.modules[old_module], name, value)
        return value

    return __getattr__
