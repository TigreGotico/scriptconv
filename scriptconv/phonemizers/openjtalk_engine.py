"""The OpenJTalk engine of the Japanese backends: pyopenjtalk-plus with onnxruntime.

Two distributions install the ``pyopenjtalk`` module: pyopenjtalk
(github.com/r9y9/pyopenjtalk) and pyopenjtalk-plus
(github.com/tsukumijima/pyopenjtalk-plus, MIT, with the OpenJTalk dictionary
under BSD-3-Clause). Their dictionaries and accent rules differ, so their
readings differ. pyopenjtalk-plus without onnxruntime turns off its model for
the reading of 何, so 何時 becomes なにじ. A backend that calls OpenJTalk runs
only on pyopenjtalk-plus with onnxruntime and the dictionary that
pyopenjtalk-plus bundles, so that the version of pyopenjtalk-plus in its
identity fixes its output. pyopenjtalk reads the variable
``OPEN_JTALK_DICT_DIR`` when it imports, and uses that dictionary in place of
its own, so the backend refuses any value but the absolute path of the
bundled dictionary.
"""
import base64
import hashlib
import os
from importlib import metadata
from pathlib import Path
from types import ModuleType
from typing import Optional

ENGINE_DISTRIBUTION = "pyopenjtalk-plus"
DICT_DIR_VARIABLE = "OPEN_JTALK_DICT_DIR"


def module_distribution(module: str, module_file: Optional[str]) -> Optional[str]:
    """The distribution whose installed files hold *module_file*.

    When both distributions are installed, both list the module's files in
    their RECORD. The one whose recorded sha256 matches the file on disk was
    installed last, and its code runs. A module with no file, such as the
    namespace package that the uninstall of one of the two leaves, has no
    owner.
    """
    if module_file is None:
        return None
    path = Path(module_file).resolve()
    digest = base64.urlsafe_b64encode(hashlib.sha256(path.read_bytes()).digest()).rstrip(b"=").decode()
    for name in metadata.packages_distributions().get(module, []):
        for file in metadata.distribution(name).files or ():
            if (file.hash is not None and file.hash.mode == "sha256" and file.hash.value == digest
                    and Path(file.locate()).resolve() == path):
                return name
    return None


def require_pyopenjtalk_plus(backend: str, requirement: str) -> ModuleType:
    """The ``pyopenjtalk`` module of pyopenjtalk-plus, with onnxruntime and the bundled dictionary.

    onnxruntime is imported first: pyopenjtalk-plus imports it while
    ``pyopenjtalk`` imports, and catches only ``ImportError`` there.

    Args:
        backend: The backend, as the messages name it.
        requirement: What installs the backend, such as
            ``"scriptconv[ja-phonemizers]"``.

    Raises:
        ImportError: If onnxruntime does not import, if no ``pyopenjtalk``
            module imports, if another distribution installed the module, or
            if ``OPEN_JTALK_DICT_DIR``, in the environment or as the module
            read it at import, is set to any path but the absolute path of
            the bundled dictionary. A relative path or a link to the bundled
            dictionary is refused too.
    """
    try:
        import onnxruntime  # noqa: F401
    except Exception as e:
        raise ImportError(
            f"{backend} needs onnxruntime, which pyopenjtalk-plus uses to read 何, and it does not "
            f"import. Run 'pip install --force-reinstall onnxruntime', or install '{requirement}'."
        ) from e
    try:
        import pyopenjtalk
    except ImportError as e:
        raise ImportError(f"{backend} needs pyopenjtalk-plus. "
                          f"Install it with 'pip install {requirement}'.") from e
    owner = module_distribution("pyopenjtalk", pyopenjtalk.__file__)
    if owner != ENGINE_DISTRIBUTION:
        raise ImportError(
            f"{backend} needs pyopenjtalk-plus, but the installed pyopenjtalk module comes from "
            f"{owner or 'an unknown distribution'}. Run 'pip uninstall pyopenjtalk', then "
            f"'pip install --force-reinstall pyopenjtalk-plus[onnxruntime]', or install "
            f"'{requirement}' in a new environment."
        )
    # pyopenjtalk opens the raw value at its first reading, maybe after a
    # change of directory or link, so the value is compared as text.
    bundled = os.path.join(os.path.dirname(os.path.abspath(pyopenjtalk.__file__)), "dictionary")
    for dict_dir in (os.environ.get(DICT_DIR_VARIABLE), os.fsdecode(pyopenjtalk.OPEN_JTALK_DICT_DIR)):
        if dict_dir is not None and os.path.normpath(dict_dir) != os.path.normpath(bundled):
            raise ImportError(
                f"{backend} reads the dictionary of pyopenjtalk-plus, but {DICT_DIR_VARIABLE} "
                f"is {dict_dir!r}, not {bundled!r}. Unset {DICT_DIR_VARIABLE}, then start "
                f"Python again."
            )
    return pyopenjtalk
