"""The ``revision`` of a backend whose phonemes come only from code and data on its own path.

A probe in a fresh process builds the backend, calls ``phonemize`` and
``phonemize_to_list`` with ``keep_punctuation`` off and on, and records each
module that the calls load and each package data file of scriptconv that they
open. The hash then covers:

- the code tokens of each scriptconv module that the probe loads, except
  ``scriptconv/version.py``;
- the bytes of each scriptconv data file that the probe opens;
- for each other distribution that holds a loaded module, the code tokens of
  each of its Python modules and the bytes of each of its other files, except a
  ``version.py`` or ``_version.py`` at the top of a package. A compiled module
  counts by its name and the version of its distribution, since its bytes
  differ by platform and by Python build;
- the source file of each class in the MRO of the backend that is not in
  scriptconv, so a subclass that changes a method changes the revision;
- the arguments that build the backend, the settings that a caller changes on
  the instance, the language and :data:`unicodedata.unidata_version`.

A code token is any token but a comment, a blank line or a string that stands
as a statement, as a docstring does. So a release that changes code or data on
the path of the backend changes the revision, and a release that changes only
docs, docstrings, ``version.py`` or the modules of other backends keeps it.
"""
import functools
import hashlib
import inspect
import io
import json
import logging
import os
import subprocess
import sys
import tokenize
import unicodedata
from importlib.metadata import packages_distributions, version
from importlib.util import find_spec
from pathlib import Path
from typing import Dict, Iterator, List, Mapping, Optional, Tuple

LOG = logging.getLogger(__name__)

FORMAT = "sc1"
"""The prefix of a revision. It changes when the inputs or the encoding of the hash change."""

#: Texts for the probe: every clause mark, a stress mark, digits and brackets.
PROBE_TEXTS = (
    "azul, a. b? c! d: e; f... g… h| i، j؛ k؟ l",
    "ázul tanemmirt",
    "16:30 «x» (y) [z] \"w\" a-b",
)

_PROBE = """
import sys
before = set(sys.modules)
opened = set()
def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        opened.add(args[0] if isinstance(args[0], str) else args[0].decode(errors="replace"))
sys.addaudithook(audit)
import importlib, json, warnings
module, qualname, lang, arguments, texts = sys.argv[1:4] + [json.loads(a) for a in sys.argv[4:6]]
backend_class = importlib.import_module(module)
for part in qualname.split("."):
    backend_class = getattr(backend_class, part)
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    for keep in (False, True):
        backend = backend_class(**arguments)
        backend.keep_punctuation = keep
        for text in texts:
            for method in (backend.phonemize, backend.phonemize_to_list):
                try:
                    method(text, lang)
                except Exception:
                    pass
modules = {name: getattr(loaded, "__file__", None)
           for name, loaded in list(sys.modules.items()) if name not in before}
print(json.dumps({"modules": modules, "opened": sorted(opened)}))
"""
"""Prints the modules that the backend loads and the files that it opens."""

_NOT_CODE = frozenset({tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER})
_LINE = frozenset({"NEWLINE", "INDENT", "DEDENT"})
_VERSION_FILES = frozenset({"version.py", "_version.py"})
_NATIVE = frozenset({".so", ".pyd", ".dll", ".dylib"})


def code_revision(backend, lang: str, arguments: Mapping, settings: Mapping) -> Optional[str]:
    """The revision of *backend* for *lang*, or ``None`` when its code cannot be read.

    *arguments* rebuild the backend in the probe, so they must be JSON values.
    *settings* are the values a caller set on the instance; they join the hash.
    """
    probed = next(cls for cls in type(backend).__mro__ if cls.__module__.startswith("scriptconv."))
    digest = hashlib.sha256(json.dumps(
        [FORMAT, f"{probed.__module__}:{probed.__qualname__}", lang, arguments, settings,
         unicodedata.unidata_version], sort_keys=True, ensure_ascii=False).encode())
    try:
        digest.update(_probe_digest(probed.__module__, probed.__qualname__, lang,
                                    json.dumps(arguments, sort_keys=True)).encode())
        for cls in type(backend).__mro__:
            if cls.__module__ in ("builtins", "abc") or cls.__module__.split(".")[0] == "scriptconv":
                continue
            path = inspect.getsourcefile(cls)
            if path is None:
                raise OSError(f"no source file for {cls.__qualname__}")
            digest.update(f"\0class\0{cls.__module__}\0{file_digest(Path(path))}".encode())
    except (OSError, TypeError, RuntimeError) as exc:
        LOG.warning("the identity of %s for %r has no revision: %s", type(backend).__name__, lang, exc)
        return None
    return f"{FORMAT}:{digest.hexdigest()}"


@functools.lru_cache(maxsize=None)
def _probe_digest(module: str, qualname: str, lang: str, arguments: str) -> str:
    """The hash of the code and data that a probe of the backend loads, for one language."""
    pythonpath = os.pathsep.join(entry or os.getcwd() for entry in sys.path)
    done = subprocess.run([sys.executable, "-P", "-c", _PROBE, module, qualname, lang, arguments,
                           json.dumps(PROBE_TEXTS)],
                          capture_output=True, text=True, env={**os.environ, "PYTHONPATH": pythonpath})
    if done.returncode:
        raise RuntimeError(f"the revision probe of {qualname} for {lang!r} failed:\n{done.stderr}")
    probe = json.loads(done.stdout.splitlines()[-1])
    modules: Dict[str, Optional[str]] = probe["modules"]
    root = Path(modules["scriptconv"]).parent
    entries: List[Tuple[str, str]] = []
    others = set()
    for name, where in modules.items():
        top = name.split(".")[0]
        if top in sys.stdlib_module_names or where is None:
            continue
        if top != "scriptconv":
            others.add(top)
        elif Path(where).relative_to(root).as_posix() != "version.py":
            entries.append((f"scriptconv/{Path(where).relative_to(root).as_posix()}",
                            file_digest(Path(where))))
    for opened in (Path(os.path.abspath(name)) for name in probe["opened"]):
        if (opened.is_relative_to(root) and opened.suffix not in (".py", ".pyc")
                and "__pycache__" not in opened.parts and opened.is_file()):
            entries.append((f"scriptconv/{opened.relative_to(root).as_posix()}", file_digest(opened)))
    for top in _distribution_tops(others):
        entries.append((top, _top_level_digest(top)))
    digest = hashlib.sha256()
    for name, value in sorted(set(entries)):
        digest.update(f"\0{name}\0{value}".encode())
    return digest.hexdigest()


def _distribution_tops(loaded: set) -> set:
    """*loaded*, and each other top-level module of a distribution that holds one of them."""
    owners = packages_distributions()
    distributions = {owner for name in loaded for owner in owners.get(name, ())}
    held = {name for name, owned in owners.items() if distributions & set(owned)}
    return (loaded | held) - {"scriptconv"}


def _top_level_digest(name: str) -> str:
    """The hash of the files of one top-level module, where the import system finds it."""
    spec = find_spec(name)
    if spec is None:
        return ""
    if spec.submodule_search_locations:
        digest = hashlib.sha256()
        for relative, path in sorted(_package_files(spec.submodule_search_locations)):
            if path.suffix in _NATIVE:
                # the file name carries the platform tag, which the hash leaves out
                relative = Path(relative).with_name(path.name.split(".")[0]).as_posix()
                value = _native(name)
            else:
                value = file_digest(path)
            digest.update(f"\0{relative}\0{value}".encode())
        return digest.hexdigest()
    if spec.origin and Path(spec.origin).is_file():
        origin = Path(spec.origin)
        return _native(name) if origin.suffix in _NATIVE else file_digest(origin)
    return ""


def _native(name: str) -> str:
    """A compiled module of the top-level module *name*: the versions of the distributions that hold it."""
    owners = sorted(set(packages_distributions().get(name, ())))
    return "native " + " ".join(f"{owner}=={version(owner)}" for owner in owners)


def _package_files(roots) -> Iterator[Tuple[str, Path]]:
    for root in map(Path, roots):
        for path in root.rglob("*"):
            relative = path.relative_to(root)
            if (path.is_file() and "__pycache__" not in relative.parts and path.suffix != ".pyc"
                    and not (len(relative.parts) == 1 and relative.name in _VERSION_FILES)):
                yield relative.as_posix(), path


def file_digest(path: Path) -> str:
    """The sha256 of the code tokens of a Python module, or of the bytes of any other file."""
    data = path.read_bytes()
    if path.suffix == ".py":
        try:
            data = json.dumps(code_tokens(data), ensure_ascii=False).encode()
        except (SyntaxError, tokenize.TokenError, UnicodeDecodeError):
            pass
    return hashlib.sha256(data).hexdigest()


def code_tokens(source: bytes) -> List[Tuple[str, str]]:
    """The tokens of a module that can change what it does.

    Comments, blank lines and strings that stand as statements, as docstrings
    do, are left out. NEWLINE, INDENT and DEDENT count with an empty string, so
    the width of an indent does not count. An f-string is one token with its
    source text, so the tokens are the same on each Python version.
    """
    encoding, _ = tokenize.detect_encoding(io.BytesIO(source).readline)
    lines = io.StringIO(source.decode(encoding), newline="\n").readlines()
    tokens: List[Tuple[str, str]] = []
    depth, start = 0, (0, 0)
    for token in tokenize.tokenize(io.BytesIO(source).readline):
        kind = tokenize.tok_name[token.type]
        if kind in ("FSTRING_START", "TSTRING_START"):
            depth, start = depth + 1, start if depth else token.start
        elif kind in ("FSTRING_END", "TSTRING_END"):
            depth -= 1
            if not depth:
                tokens.append(("STRING", _source_text(lines, start, token.end)))
        elif not depth and token.type not in _NOT_CODE:
            tokens.append((kind, "" if kind in _LINE else token.string))
    return _without_string_statements(tokens)


def _source_text(lines: List[str], start: Tuple[int, int], end: Tuple[int, int]) -> str:
    (first, first_column), (last, last_column) = start, end
    if first == last:
        return lines[first - 1][first_column:last_column]
    return lines[first - 1][first_column:] + "".join(lines[first:last - 1]) + lines[last - 1][:last_column]


def _without_string_statements(tokens: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    kept: List[Tuple[str, str]] = []
    at = 0
    while at < len(tokens):
        end = at
        while end < len(tokens) and tokens[end][0] == "STRING":
            end += 1
        starts_line = not kept or kept[-1][0] in _LINE
        if end > at and starts_line and (end == len(tokens) or tokens[end][0] == "NEWLINE"):
            at = end + 1
            continue
        kept.extend(tokens[at:max(end, at + 1)])
        at = max(end, at + 1)
    return kept
