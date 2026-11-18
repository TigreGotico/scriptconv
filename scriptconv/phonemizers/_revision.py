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
- the class of the backend, the arguments that build it, the settings that
  change the output besides the code, the language and
  :data:`unicodedata.unidata_version`.

A backend that wraps an engine with a revision of its own, as tugaphone or
orthography2ipa, names the distributions that the engine revision covers in
:meth:`~scriptconv.phonemizers.base.BasePhonemizer._covered_distributions`.
Their files leave the hash, and the backend puts the engine revision in the
settings. So a release of the engine that keeps its revision keeps the revision
of the backend, and a change of the wrapper code changes it.

For :meth:`~scriptconv.frontend.TextFrontend.identity`, a second probe reads
through a frontend, so the modules of the frontend stages count too.

A code token is any token but a comment, a blank line or a string that stands
as a statement, as a docstring does. So a release that changes code or data on
the path of the backend changes the revision, and a release that changes only
docs, docstrings, ``version.py`` or the modules of other backends keeps it.

A module on the path that does not load from a file in a directory, as from a
zip archive, raises :class:`RevisionSourceUnavailable`, so it never counts as
an empty digest. A probe that exits with an error, runs longer than
:data:`PROBE_TIMEOUT`, prints no readable result, or finds scriptconv loaded
before it starts, as from a ``sitecustomize.py``, raises
:class:`RevisionProbeFailed`. In each case :func:`code_revision` gives no
revision and logs one warning per backend, language and error in a process.
"""
import functools
import hashlib
import inspect
import io
import json
import logging
import os
import re
import subprocess
import sys
import tokenize
import unicodedata
import uuid
from importlib.metadata import packages_distributions, version
from importlib.util import find_spec
from pathlib import Path
from typing import Collection, Dict, Iterator, List, Mapping, NamedTuple, Optional, Set, Tuple, Union

LOG = logging.getLogger(__name__)

FORMAT = "sc1"
"""The prefix of a revision. It changes when the inputs or the encoding of the hash change."""

#: Texts for the probe: every clause mark, a stress mark, digits, brackets,
#: paragraphs and inline blocks.
PROBE_TEXTS = (
    "azul, a. b? c! d: e; f... g… h| i، j؛ k؟ l",
    "ázul tanemmirt",
    "16:30 «x» (y) [z] \"w\" a-b",
    "T\u00edtulo\n\nTexto [[\u02c8a]] fim. a [[ ]] b",
)

PROBE_TIMEOUT = 120
"""The seconds a probe may run before it counts as failed. A probe runs the
engine of the backend, and an engine such as tugaphone takes tens of seconds
to start on a loaded machine."""

_PROBE = """
import sys
before = set(sys.modules)
opened = set()
def audit(event, args):
    if event == "open" and isinstance(args[0], (str, bytes)):
        opened.add(args[0] if isinstance(args[0], str) else args[0].decode(errors="replace"))
sys.addaudithook(audit)
import importlib, json, warnings
marker, module, qualname, lang, mode = sys.argv[1:6]
arguments, texts = (json.loads(a) for a in sys.argv[6:8])
backend_class = importlib.import_module(module)
for part in qualname.split("."):
    backend_class = getattr(backend_class, part)
def calls(keep):
    backend = backend_class(**arguments)
    if mode == "backend":
        backend.keep_punctuation = keep
        return [lambda text: backend.phonemize(text, lang),
                lambda text: backend.phonemize_to_list(text, lang)]
    from scriptconv.frontend import Chunk, FrontendConfig, Stages, TextFrontend
    frontend = TextFrontend(FrontendConfig(lang, keep_punctuation=keep,
                                           stages=Stages(normalize=False, diacritize=False)), backend)
    return [frontend.phonemize_flat] + [
        lambda text, chunk=chunk: list(frontend.phonemize_lazy(text, Stages(chunk=chunk)))
        for chunk in Chunk]
with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    for keep in (False, True):
        for call in calls(keep):
            for text in texts:
                try:
                    call(text)
                except Exception:
                    pass
modules = {name: getattr(loaded, "__file__", None)
           for name, loaded in list(sys.modules.items()) if name not in before}
print(marker + json.dumps({"modules": modules, "opened": sorted(opened)}), flush=True)
"""
"""Prints, after a marker, the modules that a backend, or a frontend that reads
through it, loads and the files that it opens."""

LOADED_TOPS: Set[str] = set()
"""The top-level modules outside the standard library that the probes of this
process loaded, so the identity cache can watch the ones no distribution holds."""

_NOT_CODE = frozenset({tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER})
_LINE = frozenset({"NEWLINE", "INDENT", "DEDENT"})
_VERSION_FILES = frozenset({"version.py", "_version.py"})
_NATIVE = frozenset({".so", ".pyd", ".dll", ".dylib"})


class RevisionSourceUnavailable(OSError):
    """A module or package on the path of a backend has no source file in a directory to hash."""


class RevisionProbeFailed(RuntimeError):
    """The probe process failed, timed out, or gave no readable result."""


class _Failed(NamedTuple):
    """A probe that failed, kept as the name and message of its error, so a
    later call neither raises it again nor grows its traceback."""

    error: str


def _source_file(where, what: str) -> Path:
    """*where* as a path, when it is a file in a directory."""
    path = Path(where) if where else None
    if path is None or not path.is_file():
        raise RevisionSourceUnavailable(f"{what} does not load from a file in a directory: {where}")
    return path


def code_revision(backend, lang: str, settings: Mapping, frontend: bool = False) -> Optional[str]:
    """The revision of *backend* for *lang*, or ``None`` when its code cannot be read.

    The probe rebuilds the backend from ``backend._revision_arguments()``.
    *settings* are values besides the code that change the output; they join
    the hash. With *frontend*, the probe reads through a
    :class:`~scriptconv.frontend.TextFrontend`, so the modules of the frontend
    count too. The files of the distributions that
    ``backend._covered_distributions(lang)`` names leave the hash.
    """
    probed = next(cls for cls in type(backend).__mro__ if cls.__module__.startswith("scriptconv."))
    arguments = backend._revision_arguments()
    mode = "frontend" if frontend else "backend"
    digest = hashlib.sha256(json.dumps(
        [FORMAT, mode, f"{probed.__module__}:{probed.__qualname__}",
         f"{type(backend).__module__}:{type(backend).__qualname__}", lang, arguments, settings,
         unicodedata.unidata_version], sort_keys=True, ensure_ascii=False).encode())
    try:
        covered = sorted({_canonical(name) for name in backend._covered_distributions(lang)})
        outcome = _probe_outcome(probed.__module__, probed.__qualname__, lang, mode,
                                 json.dumps(arguments, sort_keys=True), json.dumps(covered))
        if isinstance(outcome, _Failed):
            _warn_once(type(backend).__name__, lang, outcome.error)
            return None
        digest.update(outcome.encode())
        for cls in type(backend).__mro__:
            if cls.__module__ in ("builtins", "abc") or cls.__module__.split(".")[0] == "scriptconv":
                continue
            path = _source_file(inspect.getsourcefile(cls), f"the class {cls.__qualname__}")
            digest.update(f"\0class\0{cls.__module__}\0{file_digest(path)}".encode())
    except (OSError, TypeError, RuntimeError) as exc:
        _warn_once(type(backend).__name__, lang, f"{type(exc).__name__}: {exc}")
        return None
    return f"{FORMAT}:{digest.hexdigest()}"


@functools.lru_cache(maxsize=None)
def _warn_once(backend: str, lang: str, error: str) -> None:
    """Logs that the identity of *backend* for *lang* has no revision, once per *error* in this process."""
    LOG.warning("the identity of %s for %r has no revision: %s", backend, lang, error)


@functools.lru_cache(maxsize=None)
def _probe_outcome(*key: str) -> Union[str, _Failed]:
    """The probe digest for *key*, or its error, kept so that a failed probe
    does not run again in this process."""
    try:
        return _run_probe(*key)
    except (RevisionProbeFailed, OSError) as exc:
        return _Failed(f"{type(exc).__name__}: {exc}")


def _run_probe(module: str, qualname: str, lang: str, mode: str, arguments: str,
               covered: str) -> str:
    """The hash of the code and data that a probe of the backend, or of a
    frontend that reads through it, loads for one language.

    *covered* is a JSON list of the distributions whose files leave the hash.

    Raises:
        RevisionProbeFailed: If the probe exits with an error, runs longer than
            :data:`PROBE_TIMEOUT`, prints no readable result after its marker,
            or finds scriptconv loaded before it starts.
    """
    pythonpath = os.pathsep.join(entry or os.getcwd() for entry in sys.path)
    marker = f"scriptconv-revision-probe-{uuid.uuid4().hex}:"
    what = f"the revision probe of {qualname} for {lang!r}"
    try:
        done = subprocess.run([sys.executable, "-P", "-c", _PROBE, marker, module, qualname, lang, mode,
                               arguments, json.dumps(PROBE_TEXTS)],
                              capture_output=True, text=True, timeout=PROBE_TIMEOUT,
                              env={**os.environ, "PYTHONPATH": pythonpath})
    except subprocess.TimeoutExpired:
        raise RevisionProbeFailed(f"{what} ran longer than {PROBE_TIMEOUT} s") from None
    if done.returncode:
        raise RevisionProbeFailed(f"{what} exited with {done.returncode}:\n{done.stderr}")
    results = [line[len(marker):] for line in done.stdout.splitlines() if line.startswith(marker)]
    if len(results) != 1:
        raise RevisionProbeFailed(f"{what} printed {len(results)} results")
    try:
        probe = json.loads(results[0])
    except ValueError as exc:
        raise RevisionProbeFailed(f"{what} printed a result that is not JSON: {exc}") from None
    modules: Dict[str, Optional[str]] = probe["modules"]
    if "scriptconv" not in modules:
        raise RevisionProbeFailed(f"{what} found scriptconv loaded before it started, "
                                  "so it cannot tell which modules the backend loads")
    root = Path(modules["scriptconv"]).parent
    entries: List[Tuple[str, str]] = []
    others = set()
    for name, where in modules.items():
        top = name.split(".")[0]
        if top in sys.stdlib_module_names or where is None:
            continue
        LOADED_TOPS.add(top)
        if top != "scriptconv":
            others.add(top)
        elif Path(where).relative_to(root).as_posix() != "version.py":
            entries.append((f"scriptconv/{Path(where).relative_to(root).as_posix()}",
                            file_digest(_source_file(where, name))))
    for opened in (Path(os.path.abspath(name)) for name in probe["opened"]):
        if (opened.is_relative_to(root) and opened.suffix not in (".py", ".pyc")
                and "__pycache__" not in opened.parts and opened.is_file()):
            entries.append((f"scriptconv/{opened.relative_to(root).as_posix()}", file_digest(opened)))
    for top in _distribution_tops(others, frozenset(json.loads(covered))):
        entries.append((top, _top_level_digest(top)))
    digest = hashlib.sha256()
    for name, value in sorted(set(entries)):
        digest.update(f"\0{name}\0{value}".encode())
    return digest.hexdigest()


def _distribution_tops(loaded: set, covered: Collection[str]) -> set:
    """*loaded*, and each other top-level module of a distribution that holds one of them,
    except those that only distributions in *covered* hold.

    A top-level module that no installed distribution holds, as a checkout on
    the import path, stands for a distribution of its own name.
    """
    owners = packages_distributions()
    distributions = {owner for name in loaded for owner in owners.get(name, ())}
    held = {name for name, owned in owners.items() if distributions & set(owned)}
    return {name for name in (loaded | held) - {"scriptconv"}
            if not {_canonical(owner) for owner in owners.get(name) or [name]} <= set(covered)}


def _canonical(distribution: str) -> str:
    """The normalised name of *distribution*, as PEP 503 gives it."""
    return re.sub(r"[-_.]+", "-", distribution).lower()


def _top_level_digest(name: str) -> str:
    """The hash of the files of one top-level module, where the import system finds it."""
    spec = find_spec(name)
    if spec is None:
        raise RevisionSourceUnavailable(f"the module {name} is not on the import path")
    if spec.submodule_search_locations:
        for location in spec.submodule_search_locations:
            if not Path(location).is_dir():
                raise RevisionSourceUnavailable(
                    f"the package {name} does not load from a directory: {location}")
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
    origin = _source_file(spec.origin, f"the module {name}")
    return _native(name) if origin.suffix in _NATIVE else file_digest(origin)


@functools.lru_cache(maxsize=None)
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
