"""The ``revision`` of a backend: a hash of the code and data on its path and of the releases under it.

The hash covers:

- the code tokens of each module of scriptconv, scriptconv-copyleft or
  scriptconv-nonfree that the backend class imports, directly or through
  another such module, and of their parent packages, except a ``version.py``
  at the top of a package. The imports are read from the source, those inside
  functions too, so a module counts whether or not a call reaches it;
- the bytes of each other file in the directory of such a module, and in each
  directory under it that is not a package, as the tables of a vendored engine.
  A package that loads only as the parent of such a module adds no files;
- the name and version of each installed distribution that the ``phonemizers``
  extra and the extra of the backend require, with the engine distribution, at
  any depth. The engine counts with its extra named by the language, when it
  has one, as ``gruut[fr]`` for ``fr``. A requirement counts when its PEP 508
  marker holds here, so a requirement under an extra that nobody asks for, or
  for another platform, does not;
- the name and version of each installed distribution that provides a module
  that the modules above import at module level, in a ``try`` block or not, as
  num2words for the Shami normaliser. The requirements of such a distribution
  do not count. A distribution that these modules import only inside a
  function does not count, unless an extra above requires it. So an optional
  tool that a backend loads inside a function, as the camel-tools diacritizer
  of the Shami backend, is not in the revision;
- scriptconv and its sister packages count by their files instead of their
  version, and the distributions of
  :meth:`~scriptconv.phonemizers.base.BasePhonemizer._covered_distributions`
  count by the engine revision or version in the settings;
- the source file of each class in the MRO of the backend outside these packages;
- the class of the backend, the arguments that build it, the settings that
  change the output besides the code, whether the backend keeps clause
  punctuation, the language and :data:`unicodedata.unidata_version`.

With *frontend*, the modules that :mod:`scriptconv.frontend` imports count too.

A code token is any token but a comment, a blank line or a string that stands
as a statement, as a docstring does. So a release that changes code or data on
the path of the backend changes the revision, and a release that changes only
docs, ``version.py`` or the modules and data of other backends keeps it. A
release of a distribution above changes it. A release of any other
distribution keeps it, also when the backend imports that distribution inside
a function, or loads it at run time through a name that is not in its source.

Nothing of the running process counts: neither the modules it loaded, nor its
working directory, nor a package that loads at startup. Two machines with the
same packages give the same revision. An edit of a dependency's files that
keeps its version, as in an editable install, keeps the revision.

A module of these packages that does not load from a file in a directory, as
from a zip archive, or a scriptconv with no installed metadata, gives no
revision and one warning per backend, language and error in a process.
"""
import ast
import functools
import hashlib
import inspect
import io
import json
import logging
import os
import platform
import re
import sys
import tokenize
import unicodedata
from importlib import metadata
from importlib.util import find_spec
from pathlib import Path
from typing import Collection, Dict, FrozenSet, Iterator, List, Mapping, Optional, Set, Tuple

LOG = logging.getLogger(__name__)

FORMAT = "sc2"
"""The prefix of a revision. It changes when the inputs or the encoding of the hash change."""

_NOT_CODE = frozenset({tokenize.COMMENT, tokenize.NL, tokenize.ENCODING, tokenize.ENDMARKER})
_LINE = frozenset({"NEWLINE", "INDENT", "DEDENT"})
#: The packages whose files the hash holds.
_IN_TREE = frozenset({"scriptconv", "scriptconv_copyleft", "scriptconv_nonfree"})
_IN_TREE_DISTRIBUTIONS = frozenset({"scriptconv", "scriptconv-copyleft", "scriptconv-nonfree"})
_REQUIREMENT = re.compile(r"\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?[^;]*(?:;(.*))?")
_COMPARISON = re.compile(r"""(\w+|"[^"]*"|'[^']*')\s*(===|==|!=|~=|<=|>=|<|>|not\s+in\b|in\b)\s*(\w+|"[^"]*"|'[^']*')""")
_VERSION = re.compile(r"\d+(?:\.\d+)*")
#: The values of the PEP 508 marker variables in this interpreter.
_ENVIRONMENT = {
    "implementation_name": sys.implementation.name,
    "implementation_version": platform.python_version() if sys.implementation.name == "cpython"
    else ".".join(map(str, sys.implementation.version[:3])),
    "os_name": os.name, "platform_machine": platform.machine(), "platform_release": platform.release(),
    "platform_system": platform.system(), "platform_version": platform.version(),
    "platform_python_implementation": platform.python_implementation(),
    "python_full_version": platform.python_version(), "python_version": "%s.%s" % sys.version_info[:2],
    "sys_platform": sys.platform,
}


class RevisionSourceUnavailable(OSError):
    """A module or package on the path of a backend has no source file in a directory to hash."""


def _source_file(where, what: str) -> Path:
    """*where* as a path, when it is a file in a directory."""
    path = Path(where) if where else None
    if path is None or not path.is_file():
        raise RevisionSourceUnavailable(f"{what} does not load from a file in a directory: {where}")
    return path


def code_revision(backend, lang: str, settings: Mapping, frontend: bool = False) -> Optional[str]:
    """The revision of *backend* for *lang*, or ``None`` when its code cannot be read.

    *settings* are values besides the code that change the output; they join
    the hash. With *frontend*, the modules of :mod:`scriptconv.frontend` count too.
    """
    in_tree = [cls for cls in type(backend).__mro__ if cls.__module__.partition(".")[0] in _IN_TREE]
    if inspect.isabstract(in_tree[0]):
        # a backend class from elsewhere on BasePhonemizer itself, which says nothing of its path
        return None
    roots = {cls.__module__ for cls in in_tree} | ({"scriptconv.frontend"} if frontend else set())
    try:
        classes = [(cls.__module__, file_digest(_source_file(inspect.getsourcefile(cls), f"the class {cls.__qualname__}")))
                   for cls in type(backend).__mro__
                   if cls.__module__ not in ("builtins", "abc") and cls not in in_tree]
        files, outside = _path(frozenset(roots))
        extras = {"phonemizers", _extra(type(backend))} - {None}
        roots_of_releases = [("scriptconv", frozenset(extras))]
        imported = {name for top in outside for name in _top_level_distributions().get(top, ())}
        if backend.engine_distribution is not None:
            # an engine extra named by the language, as gruut[fr], holds the data of that language
            language = _canonical(lang)
            roots_of_releases.append((backend.engine_distribution,
                                      frozenset({language, language.partition("-")[0]})))
        covered = {_canonical(name) for name in backend._covered_distributions(lang)}
        hashed = [FORMAT, "frontend" if frontend else "backend",
                  f"{type(backend).__module__}:{type(backend).__qualname__}", lang,
                  backend._revision_arguments(), settings, backend._keeps_punctuation(),
                  unicodedata.unidata_version, files, classes,
                  _releases(roots_of_releases, covered, imported)]
    except (OSError, SyntaxError, ValueError, KeyError, TypeError, metadata.PackageNotFoundError) as exc:
        _warn_once(type(backend).__name__, lang, f"{type(exc).__name__}: {exc}")
        return None
    digest = hashlib.sha256(json.dumps(hashed, sort_keys=True, ensure_ascii=False).encode())
    return f"{FORMAT}:{digest.hexdigest()}"


@functools.lru_cache(maxsize=None)
def _warn_once(backend: str, lang: str, error: str) -> None:
    """Logs that the identity of *backend* for *lang* has no revision, once per *error* in this process."""
    LOG.warning("the identity of %s for %r has no revision: %s", backend, lang, error)


def _extra(backend_class) -> Optional[str]:
    """The scriptconv extra that installs the first registered class in the MRO of *backend_class*."""
    from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY
    extras = {cls_name: extra for _, cls_name, extra in PHONEMIZER_REGISTRY.values()}
    return next((extras[cls.__name__] for cls in backend_class.__mro__ if cls.__name__ in extras), None)


def _canonical(name: str) -> str:
    """The normalised name of a distribution or an extra, as PEP 503 and PEP 685 give it."""
    return re.sub(r"[-_.]+", "-", name).lower()


@functools.lru_cache(maxsize=None)
def _top_level_distributions() -> Mapping[str, List[str]]:
    """The installed distributions that provide each top-level module."""
    return metadata.packages_distributions()


@functools.lru_cache(maxsize=None)
def _path(roots: FrozenSet[str]) -> Tuple[List[Tuple[str, str]], FrozenSet[str]]:
    """The path and digest of each file of the packages in :data:`_IN_TREE` on the import path of *roots*,
    and the top-level name of each other module that these files import at module level."""
    modules: Dict[str, Path] = {}
    imported = set(roots)
    outside: Set[str] = set()
    pending = list(roots)
    while pending:
        name = pending.pop()
        if name in modules:
            continue
        path = _module_file(name)
        if path is None:
            # a name imported from a module, as GraphemePhonemizer in "from scriptconv.phonemizers import ..."
            continue
        modules[name] = path
        package = name if path.name == "__init__.py" else name.rpartition(".")[0]
        pending.extend(package.rsplit(".", depth)[0] for depth in range(package.count(".") + 1))
        for module, names, module_level in _imported(path, package):
            top = module.partition(".")[0]
            if top not in _IN_TREE:
                # an import inside a function serves another language, or a dependency that an extra declares
                if module_level:
                    outside.add(top)
                continue
            submodules = [f"{module}.{name}" for name in names]
            pending.append(module)
            pending.extend(submodules)
            imported.update(submodules)
            # "from package import module" loads the package only as a parent
            if not names or not all(map(_module_file, submodules)):
                imported.add(module)
    sites = {name.partition(".")[0]: path.parents[name.count(".") + (path.name == "__init__.py")]
             for name, path in modules.items()}
    files = {(name.partition(".")[0], path) for name, path in modules.items()}
    # a package that loads only as the parent of an imported module, as _thirdparty, adds no data files
    files |= {(name.partition(".")[0], data) for name, path in modules.items() if name in imported
              for data in _data_files(path.parent)}
    entries = []
    for top, path in files:
        relative = path.relative_to(sites[top]).as_posix()
        if relative != f"{top}/version.py":
            entries.append((relative, file_digest(path)))
    return sorted(entries), frozenset(outside)


def _module_file(name: str) -> Optional[Path]:
    """The source file of the module *name*, or ``None`` when *name* is no installed module."""
    top, _, rest = name.partition(".")
    spec = find_spec(top)
    if spec is None:
        return None
    locations = spec.submodule_search_locations or []
    if not locations or not all(Path(location).is_dir() for location in locations):
        raise RevisionSourceUnavailable(f"the package {top} does not load from a directory: {spec.origin}")
    for location in locations:
        base = Path(location).joinpath(*rest.split(".")) if rest else Path(location)
        for path in (base / "__init__.py", base.with_name(base.name + ".py")):
            if path.is_file():
                return path
    return None


def _imported(path: Path, package: str) -> Iterator[Tuple[str, Tuple[str, ...], bool]]:
    """Each module that the source at *path*, a module of *package*, may import, with the names it imports from it,
    and whether the import runs at module level, that is outside any function."""
    pending: List[Tuple[ast.AST, bool]] = [(ast.parse(path.read_bytes()), True)]
    while pending:
        node, module_level = pending.pop()
        if isinstance(node, ast.Import):
            yield from ((alias.name, (), module_level) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                parent = package.rsplit(".", node.level - 1)[0]
                module = f"{parent}.{module}" if module else parent
            yield module, tuple(alias.name for alias in node.names), module_level
        else:
            inner = module_level and not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            # an import is a statement, so the walk skips expressions
            pending.extend((child, inner) for child in ast.iter_child_nodes(node)
                           if isinstance(child, (ast.stmt, ast.excepthandler, ast.match_case)))


def _data_files(directory: Path) -> Iterator[Path]:
    """The files of *directory* that are not Python, and each file under it outside a package."""
    for path in directory.iterdir():
        if path.is_file() and path.suffix not in (".py", ".pyc"):
            yield path
        elif path.is_dir() and path.name != "__pycache__" and not (path / "__init__.py").exists():
            yield from (child for child in path.rglob("*")
                        if child.is_file() and "__pycache__" not in child.parts and child.suffix != ".pyc")


def _releases(roots: List[Tuple[str, FrozenSet[str]]], covered: Collection[str],
              imported: Collection[str] = ()) -> List[str]:
    """``name==version`` of each installed distribution that *roots*, as (distribution, extras), require at any depth,
    and of each distribution in *imported*, without its requirements.

    A distribution that is not installed, as an optional engine or a binary,
    adds nothing. The distributions of :data:`_IN_TREE_DISTRIBUTIONS` and
    *covered* stay out, and their requirements count.
    """
    found: Dict[str, str] = {}
    for name in imported:
        try:
            found[_canonical(name)] = metadata.distribution(name).version
        except metadata.PackageNotFoundError:
            continue
    seen: Set[Tuple[str, str]] = set()
    pending = [(name, extra) for name, extras in roots for extra in ("", *extras)]
    while pending:
        name, extra = pending.pop()
        key = (_canonical(name), _canonical(extra))
        if key in seen:
            continue
        seen.add(key)
        try:
            distribution = metadata.distribution(name)
        except metadata.PackageNotFoundError:
            if key[0] == "scriptconv":
                raise
            continue
        found[key[0]] = distribution.version
        for requirement in distribution.requires or ():
            required, extras, marker = _REQUIREMENT.match(requirement).groups()
            if marker is None or _marker_holds(marker, key[1]):
                pending.extend((required, extra) for extra in ("", *(extras or "").replace(" ", "").split(",")))
    return sorted(f"{name}=={version}" for name, version in found.items()
                  if name not in _IN_TREE_DISTRIBUTIONS and name not in covered)


def _marker_holds(marker: str, extra: str) -> bool:
    """Whether the PEP 508 environment *marker* holds in this interpreter, with *extra* asked for."""
    environment = {**_ENVIRONMENT, "extra": extra}

    def compare(match: re.Match) -> str:
        left, right = (side[1:-1] if side[0] in "\"'" else environment[side] for side in (match[1], match[3]))
        operator = " ".join(match[2].split())
        if "extra" in (match[1], match[3]):
            left, right = _canonical(left), _canonical(right)
        if operator in ("in", "not in"):
            return str((left in right) == (operator == "in"))
        if operator != "===" and _VERSION.fullmatch(left) and _VERSION.fullmatch(right):
            given = [int(part) for part in right.split(".")]
            width = max(left.count("."), right.count(".")) + 1
            left, right = ([*map(int, value.split(".")), *[0] * width][:width] for value in (left, right))
            if operator == "~=":
                return str(left >= right and left[:len(given) - 1] == given[:-1])
        return str({"===": left == right, "==": left == right, "!=": left != right, "<": left < right,
                    "<=": left <= right, ">": left > right, ">=": left >= right, "~=": left >= right}[operator])

    expression = _COMPARISON.sub(compare, marker)
    if not re.fullmatch(r"(?:\s|\(|\)|True|False|and|or)*", expression):
        raise ValueError(f"a requirement marker that PEP 508 does not allow: {marker}")
    return eval(expression, {"__builtins__": {}})


@functools.lru_cache(maxsize=None)
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
    """The source from *start* to *end*, two (line, column) positions of :mod:`tokenize` with lines from 1."""
    (first, first_column), (last, last_column) = start, end
    if first == last:
        return lines[first - 1][first_column:last_column]
    return lines[first - 1][first_column:] + "".join(lines[first:last - 1]) + lines[last - 1][:last_column]


def _without_string_statements(tokens: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """*tokens* without each run of strings that is a whole statement, as a docstring is, and its NEWLINE."""
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
