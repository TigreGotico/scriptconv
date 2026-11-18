"""A disk cache for :meth:`~scriptconv.frontend.TextFrontend.identity`.

The first ``identity()`` of a frontend runs the revision probes, which take
seconds. The cache keeps the result in a JSON file under the user cache
directory, so a later process reads it back in a few milliseconds, with no
probe and no call into the backend.

An entry is found by a hash of its key: the interpreter path and version,
the ``sys.path`` entries, :data:`unicodedata.unidata_version`, the backend
class, its constructor
arguments and instance settings, and the frontend settings that the revision
hashes, the resolved language among them. The entry then holds the size and
modification time of each file that can change the identity. A hit needs each
of them to be the same:

- each ``sys.path`` directory, which changes when a distribution is installed
  in it or removed from it;
- the ``RECORD`` of each distribution, or the ``PKG-INFO`` of an egg, in a
  ``sys.path`` directory, which changes when the distribution is reinstalled;
- each file and directory of each loaded package that no ``RECORD`` lists
  where it loads from: an editable install, a checkout on the import path, or
  a checkout that shadows an installed distribution;
- the source file of each class of the backend outside scriptconv.

Only an identity with a ``revision`` is kept. An identity with none can carry
a version that comes from outside Python, such as the espeak-ng binary, which
no key file follows.

An entry is written to a temporary file in the cache directory and renamed
into place, so two processes that write one entry leave one whole entry. An
entry that cannot be read or parsed is a miss. A cache directory that cannot
be written gives no entry and no error.
"""
import dataclasses
import hashlib
import inspect
import json
import logging
import os
import sys
import tempfile
import unicodedata
from importlib.metadata import PackageNotFoundError, distribution, packages_distributions
from importlib.util import find_spec
from pathlib import Path
from typing import Iterator, List, Mapping, Optional, Set, Tuple

from scriptconv.phonemizers.base import PhonemizerIdentity

LOG = logging.getLogger(__name__)

FORMAT = 1
"""The version of the entry format. It changes when the key or the entry change."""

Stat = Tuple[str, int, int]


def cache_dir() -> Path:
    """The directory of the entries, under the user cache directory of the platform."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Caches"
    else:
        base = os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache"
    return Path(base) / "scriptconv" / "identity"


def key(backend, settings: Mapping) -> dict:
    """The key of the identity of a frontend with *backend* and the frontend *settings*."""
    return {"format": FORMAT, "python": [sys.executable, sys.version],
            "path": [os.path.abspath(entry or os.getcwd()) for entry in sys.path],
            "unicode": unicodedata.unidata_version,
            "backend": f"{type(backend).__module__}:{type(backend).__qualname__}",
            "arguments": backend._revision_arguments(), "instance": backend._identity_settings(),
            "frontend": dict(settings)}


def _entry_path(entry_key: dict) -> Path:
    text = json.dumps(entry_key, sort_keys=True, ensure_ascii=False)
    return cache_dir() / f"{hashlib.sha256(text.encode()).hexdigest()}.json"


def load(entry_key: dict) -> Optional[PhonemizerIdentity]:
    """The identity kept for *entry_key*, or ``None`` when no entry matches."""
    try:
        entry = json.loads(_entry_path(entry_key).read_text(encoding="utf-8"))
        if entry["key"] != json.loads(json.dumps(entry_key)):
            return None
        for name, size, mtime in entry["files"]:
            stat = os.stat(name)
            if (stat.st_size, stat.st_mtime_ns) != (size, mtime):
                return None
        return PhonemizerIdentity(**entry["identity"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def store(entry_key: dict, identity: PhonemizerIdentity, backend) -> None:
    """Keeps *identity* for *entry_key*, with the key files of *backend*."""
    if identity.revision is None:
        return
    path = _entry_path(entry_key)
    try:
        # before the stats, as the new directory can change the time of a watched one
        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.stem, suffix=".tmp")
    except OSError as exc:
        LOG.debug("the identity cache cannot write in %s: %s", path.parent, exc)
        return
    entry = {"key": entry_key, "files": watched(backend), "identity": dataclasses.asdict(identity)}
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as written:
            json.dump(entry, written, ensure_ascii=False)
        os.replace(temporary, path)
    except OSError as exc:
        LOG.debug("the identity cache cannot write %s: %s", path, exc)
        Path(temporary).unlink(missing_ok=True)


def watched(backend) -> List[Stat]:
    """The size and modification time of each file that can change the identity of *backend*."""
    names: Set[str] = set()
    for entry in sys.path:
        directory = Path(entry or os.getcwd())
        if not directory.is_dir():
            continue
        names.add(str(directory.resolve()))
        names.update(str(path) for pattern in ("*.dist-info/RECORD", "*.egg-info/PKG-INFO", "*.egg-info")
                     for path in directory.glob(pattern) if path.is_file())
    for root in _unrecorded_roots():
        names.update(str(path) for path in _tree(root))
    for cls in type(backend).__mro__:
        if cls.__module__.split(".")[0] not in ("scriptconv", "builtins", "abc"):
            source = inspect.getsourcefile(cls)
            if source:
                names.add(source)
    stats = []
    for name in sorted(names):
        try:
            stat = os.stat(name)
        except OSError:
            continue
        stats.append((name, stat.st_size, stat.st_mtime_ns))
    return stats


def _unrecorded_roots() -> Iterator[Path]:
    """The directory or file of each loaded top-level module that no
    ``RECORD`` lists where it loads from: a module of an editable install, a
    checkout on the import path, or a module that shadows an installed one."""
    from scriptconv.phonemizers._revision import LOADED_TOPS
    owners = packages_distributions()
    loaded = LOADED_TOPS | {name.split(".")[0] for name in list(sys.modules)}
    for top in sorted(loaded - set(sys.stdlib_module_names) - set(sys.builtin_module_names)):
        try:
            spec = find_spec(top)
        except (ImportError, ValueError):
            continue
        if spec is None:
            continue
        if spec.submodule_search_locations:
            locations = [Path(location) for location in spec.submodule_search_locations]
        elif spec.origin and Path(spec.origin).is_file():
            locations = [Path(spec.origin)]
        else:
            continue
        if not all(_recorded(location, owners.get(top, ())) for location in locations):
            yield from locations


def _recorded(location: Path, owners) -> bool:
    """Whether a distribution in *owners* holds *location* in its own
    installation directory. The source tree of an editable install is outside it."""
    for name in owners:
        try:
            root = Path(distribution(name).locate_file("")).resolve()
        except PackageNotFoundError:
            continue
        if location.resolve().is_relative_to(root):
            return True
    return False


def _tree(root: Path) -> Iterator[Path]:
    """*root*, and each directory and file under it but bytecode caches."""
    yield root
    if root.is_dir():
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [name for name in subdirectories if name != "__pycache__"]
            yield from (Path(directory) / name for name in subdirectories + files)
