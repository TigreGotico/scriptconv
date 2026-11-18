"""A disk cache for :meth:`~scriptconv.frontend.TextFrontend.identity`.

The first ``identity()`` of a frontend runs the revision probes, which take
seconds. The cache keeps the result in a JSON file under the user cache
directory, so a later process reads it back in a few milliseconds, with no
probe and no call into the backend.

An entry is found by a hash of its key: the interpreter path and version,
the ``sys.path`` entries, :data:`unicodedata.unidata_version`, the backend
class, its constructor arguments and instance settings, and the frontend
settings that the revision hashes, the resolved language among them. The
entry then holds the state of each file and directory that can change the
identity, taken before the identity is computed. A hit needs each of them to
be the same:

- the names in each ``sys.path`` directory, which change when a distribution
  is installed in it or removed from it;
- the size and modification time of the ``RECORD`` of each distribution, or
  the ``PKG-INFO`` of an egg, in a ``sys.path`` directory, which change when
  the distribution is reinstalled;
- each package and module of each source tree that no ``RECORD`` lists: each
  ``sys.path`` directory that is not a site or standard library directory,
  such as a checkout on ``PYTHONPATH`` or the target of a ``.pth`` file, and
  the project of each editable install. A file counts by its size and
  modification time, a directory by its names. Each of them is watched,
  whether or not this process loads it, because a revision probe can load
  what the process that writes the entry does not;
- the source file of each class of the backend outside scriptconv.

A directory counts by its names and not by its modification time, so the
``__pycache__`` that the computation writes does not change the entry.

Only an identity with a ``revision`` is kept. An identity with none can carry
a version that comes from outside Python, such as the espeak-ng binary, which
no key file follows.

An entry is written to a temporary file in the cache directory and renamed
into place, so two processes that write one entry leave one whole entry. An
entry that cannot be read or parsed is a miss. A cache directory that cannot
be written gives no entry and no error.
"""
import ast
import dataclasses
import hashlib
import inspect
import json
import logging
import os
import re
import site
import sys
import sysconfig
import tempfile
import unicodedata
from pathlib import Path
from typing import Iterator, List, Mapping, Optional, Set, Tuple
from urllib.parse import urlparse
from urllib.request import url2pathname

from scriptconv.phonemizers.base import PhonemizerIdentity

LOG = logging.getLogger(__name__)

FORMAT = 3
"""The version of the entry format. It changes when the key or the entry change."""

Stat = Tuple[str, int, int]
"""A file, its size and its modification time in nanoseconds."""

Listing = Tuple[str, str]
"""A directory, and a digest of the names in it but ``__pycache__``."""

_MAPPING = re.compile(r"^MAPPING\s*(?::[^=]*)?=\s*(\{.*?\})\s*$", re.MULTILINE | re.DOTALL)


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
        for name, digest in entry["directories"]:
            if _listing(name) != digest:
                return None
        return PhonemizerIdentity(**entry["identity"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def snapshot(backend) -> Optional[dict]:
    """The state of the key files of *backend*, to take before its identity is
    computed, or ``None`` when the cache directory cannot be written. A change
    that lands while the identity is computed then gives a miss and never a
    stale entry."""
    try:
        # before the state, as a new cache directory can change a watched one
        cache_dir().mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        LOG.debug("the identity cache cannot write in %s: %s", cache_dir(), exc)
        return None
    return watched(backend)


def store(entry_key: dict, identity: PhonemizerIdentity, state: Optional[dict]) -> None:
    """Keeps *identity* for *entry_key*, with the *state* that :func:`snapshot`
    took before the identity was computed."""
    if identity.revision is None or state is None:
        return
    path = _entry_path(entry_key)
    entry = {"key": entry_key, **state, "identity": dataclasses.asdict(identity)}
    try:
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.stem, suffix=".tmp")
    except OSError as exc:
        LOG.debug("the identity cache cannot write in %s: %s", path.parent, exc)
        return
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as written:
            json.dump(entry, written, ensure_ascii=False)
        os.replace(temporary, path)
    except OSError as exc:
        LOG.debug("the identity cache cannot write %s: %s", path, exc)
        Path(temporary).unlink(missing_ok=True)


def watched(backend) -> dict:
    """The state of each file and directory that can change the identity of
    *backend*: ``files`` as :data:`Stat` and ``directories`` as :data:`Listing`."""
    files: Set[str] = set()
    directories: Set[str] = set()
    sites = _site_directories()
    sources: Set[Path] = set()
    for entry in sys.path:
        directory = Path(entry or os.getcwd()).resolve()
        if not directory.is_dir():
            continue
        directories.add(str(directory))
        files.update(str(path) for pattern in ("*.dist-info/RECORD", "*.egg-info/PKG-INFO", "*.egg-info")
                     for path in directory.glob(pattern) if path.is_file())
        if directory in sites:
            sources.update(_editable_sources(directory))
        else:
            sources.add(directory)
    for source in sources:
        for root in _importable(source):
            for path in _tree(root):
                (directories if path.is_dir() else files).add(str(path))
    for cls in type(backend).__mro__:
        if cls.__module__.split(".")[0] not in ("scriptconv", "builtins", "abc"):
            source_file = inspect.getsourcefile(cls)
            if source_file:
                files.add(source_file)
    stats: List[Stat] = []
    for name in sorted(files):
        try:
            stat = os.stat(name)
        except OSError:
            continue
        stats.append((name, stat.st_size, stat.st_mtime_ns))
    listings: List[Listing] = []
    for name in sorted(directories):
        try:
            listings.append((name, _listing(name)))
        except OSError:
            continue
    return {"files": stats, "directories": listings}


def _listing(directory: str) -> str:
    names = sorted(name for name in os.listdir(directory) if name != "__pycache__")
    return hashlib.sha256("\0".join(names).encode()).hexdigest()


def _site_directories() -> Set[Path]:
    """The site directories, whose files a ``RECORD`` lists, and each
    ``sys.path`` directory of the standard library, which the interpreter
    version fixes."""
    library = [Path(sysconfig.get_path(name)).resolve() for name in ("stdlib", "platstdlib")]
    sites = {Path(name).resolve() for name in (*site.getsitepackages(), site.getusersitepackages(),
                                               sysconfig.get_path("purelib"), sysconfig.get_path("platlib"))}
    return sites | {Path(entry).resolve() for entry in sys.path
                    if entry and any(Path(entry).resolve().is_relative_to(root) for root in library)}


def _editable_sources(directory: Path) -> Iterator[Path]:
    """The source trees of the editable installs in the site *directory*: the
    project of each ``direct_url.json`` with ``dir_info.editable``, and each
    path in the ``MAPPING`` of a setuptools ``__editable__`` finder."""
    for direct_url in directory.glob("*.dist-info/direct_url.json"):
        try:
            record = json.loads(direct_url.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        url = urlparse(record.get("url", ""))
        if record.get("dir_info", {}).get("editable") and url.scheme == "file":
            project = Path(url2pathname(url.path))
            yield project
            yield project / "src"
    for finder in directory.glob("__editable__*finder.py"):
        try:
            found = _MAPPING.search(finder.read_text(encoding="utf-8"))
            mapping = ast.literal_eval(found.group(1)) if found else {}
        except (OSError, ValueError, SyntaxError):
            continue
        for location in mapping.values():
            yield Path(location).parent


def _importable(directory: Path) -> Iterator[Path]:
    """The packages and modules at the top of the source tree *directory*."""
    try:
        children = list(directory.iterdir())
    except OSError:
        return
    for child in children:
        if child.suffix == ".py" and child.is_file():
            yield child
        elif (child / "__init__.py").is_file():
            yield child


def _tree(root: Path) -> Iterator[Path]:
    """*root*, and each directory and file under it but bytecode caches."""
    yield root
    if root.is_dir():
        for directory, subdirectories, files in os.walk(root):
            subdirectories[:] = [name for name in subdirectories if name != "__pycache__"]
            yield from (Path(directory) / name for name in subdirectories + files)
