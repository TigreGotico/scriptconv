"""The OpenJTalk engine of the Japanese backends: pyopenjtalk-plus with onnxruntime.

Two distributions install the ``pyopenjtalk`` module: pyopenjtalk
(github.com/r9y9/pyopenjtalk) and pyopenjtalk-plus
(github.com/tsukumijima/pyopenjtalk-plus, MIT, with the OpenJTalk dictionary
under BSD-3-Clause). Their dictionaries and accent rules differ, so their
readings differ. pyopenjtalk-plus without onnxruntime turns off its model for
the reading of 何, so 何時 becomes なにじ. A backend that calls OpenJTalk runs
only on pyopenjtalk-plus with onnxruntime, so that the version of
pyopenjtalk-plus in its identity fixes its output.
"""
import base64
import hashlib
from importlib import metadata
from pathlib import Path
from types import ModuleType
from typing import Optional

ENGINE_DISTRIBUTION = "pyopenjtalk-plus"


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
    """The ``pyopenjtalk`` module, if pyopenjtalk-plus installed it and onnxruntime imports.

    onnxruntime is imported first: pyopenjtalk-plus imports it while
    ``pyopenjtalk`` imports, and catches only ``ImportError`` there.

    Args:
        backend: The backend, as the messages name it.
        requirement: What installs the backend, such as
            ``"scriptconv[ja-phonemizers]"``.

    Raises:
        ImportError: If onnxruntime does not import, if no ``pyopenjtalk``
            module imports, or if another distribution installed the module.
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
    return pyopenjtalk
