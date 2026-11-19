#!/usr/bin/env python3
"""Fail when an extra of scriptconv pulls a copyleft or non-commercial distribution.

Each extra of ``pyproject.toml`` is expanded (a ``scriptconv[x]`` entry is
replaced by the entries of ``x``) and resolved with ``uv pip compile`` for
Python 3.11 and 3.13. The licence of every resolved pin is read from the
PyPI JSON API of that exact version: ``license_expression``, else the
``License ::`` classifiers, else the ``license`` field.

scriptconv-copyleft and scriptconv-nonfree are the declared homes of the
restricted wrappers, so they and what only they pull are left out of the
resolution. Two names are allowed by ruling, with the reason in the README:
``distance`` and ``num2words``.

The script needs ``uv`` on ``PATH`` and network access to PyPI. CI runs it on
every pull request (``.github/workflows/extra_licences.yml``).

Usage: python scripts/check_extra_licences.py [extra ...]
"""
import json
import re
import subprocess
import sys
import tempfile
import tomllib
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYTHONS = ("3.11", "3.13")
SISTERS = {"scriptconv-copyleft", "scriptconv-nonfree"}

#: Allowed by ruling; see the Licensing section of the README.
WHITELIST = {"distance", "num2words"}

#: Restricted by ruling, whatever their metadata says.
DENIED = {
    "vinorm": "free for non-commercial use only, ships a binary with no source",
    "viphoneme": "free for non-commercial use only",
    "africa-g2p": "language data has no licence grant beyond research",
    "ghana-g2p": "uses the africa-g2p language data",
}

#: Distributions with no licence metadata, read from upstream.
KNOWN = {
    "transphone": "MIT",  # LICENSE in the wheel
    "phonikud": "CC-BY-4.0",  # repository LICENSE
    "phonikud-onnx": "CC-BY-4.0",  # its source is in the phonikud repository
    "eng-to-ipa": "MIT",  # repository LICENSE
    "tokenizers": "Apache-2.0",  # repository LICENSE; release candidates carry no metadata
    "httpx": "BSD-3-Clause",  # repository LICENSE; dev releases carry no metadata
}

RESTRICTED = re.compile(
    r"\bA?GPL|\bLGPL|GNU (Affero |Lesser |Library )?General Public|"
    r"NonCommercial|non-commercial|\bNC\b|CC-BY-NC|by-nc|"
    r"EUPL|SSPL|BUSL|all rights reserved", re.IGNORECASE)
# NVIDIA's CUDA wheels are proprietary and allow commercial use.
PROPRIETARY_OK = re.compile(r"^(nvidia-|cuda-)")


def expand(extras, name, seen=()):
    """The requirement strings of extra *name*, with scriptconv[...] expanded."""
    out = []
    for req in extras[name]:
        match = re.match(r"scriptconv\[([^\]]+)\]", req)
        if match:
            for inner in match.group(1).split(","):
                if inner not in seen:
                    out += expand(extras, inner.strip(), (*seen, name))
        else:
            out.append(req)
    return out


def requirement_name(req):
    return re.split(r"[\[<>=!~;@ ]", req, maxsplit=1)[0].lower().replace("_", "-")


def resolve(reqs, python):
    with tempfile.TemporaryDirectory() as tmp:
        infile = Path(tmp) / "requirements.in"
        infile.write_text("\n".join(reqs) + "\n", encoding="utf-8")
        result = subprocess.run(
            ["uv", "pip", "compile", str(infile), "--prerelease=allow", "--no-header",
             "--no-annotate", "--no-config", "--python-version", python,
             "--python-platform", "x86_64-manylinux_2_28"],
            capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"uv pip compile failed for {reqs}:\n{result.stderr}")
    pins = {}
    for line in result.stdout.splitlines():
        line = line.split("#")[0].strip()
        if "==" in line:
            name, version = line.split("==")
            pins[requirement_name(name)] = version.split(";")[0].strip()
    return pins


_CACHE = {}


def licence(name, version):
    """``(source, text)``: what PyPI records as the licence of this exact release.

    *source* is ``"expression"`` for an SPDX ``license_expression``, else
    ``"classifiers"`` or ``"text"``, or ``"known"`` from :data:`KNOWN`.
    """
    key = (name, version)
    if key not in _CACHE:
        with urllib.request.urlopen(f"https://pypi.org/pypi/{name}/{version}/json",
                                    timeout=60) as response:
            info = json.load(response)["info"]
        classifiers = [c.split(" :: ")[-1] for c in info.get("classifiers") or []
                       if c.startswith("License ::")]
        if info.get("license_expression"):
            _CACHE[key] = ("expression", info["license_expression"])
        elif classifiers:
            _CACHE[key] = ("classifiers", "; ".join(classifiers))
        elif (info.get("license") or "").strip():
            _CACHE[key] = ("text", info["license"].strip()[:300])
        else:
            _CACHE[key] = ("known", KNOWN.get(name, ""))
    return _CACHE[key]


def restricted_expression(expression):
    """True when every choice the SPDX *expression* offers is restricted."""
    tokens = re.findall(r"[()]|[^\s()]+", expression)
    pos = 0

    def any_of():  # OR: restricted only when each side is
        nonlocal pos
        value = all_of()
        while pos < len(tokens) and tokens[pos] == "OR":
            pos += 1
            value = all_of() and value
        return value

    def all_of():  # AND, WITH: restricted when either side is
        nonlocal pos
        value = atom()
        while pos < len(tokens) and tokens[pos] in ("AND", "WITH"):
            pos += 1
            value = atom() or value
        return value

    def atom():
        nonlocal pos
        token = tokens[pos]
        pos += 1
        if token == "(":
            value = any_of()
            pos += 1  # the closing ")"
            return value
        return bool(RESTRICTED.search(token))

    return any_of()


def verdict(name, version):
    """``(kind, text)`` with kind one of allowed, whitelisted, restricted, unknown."""
    if name in DENIED:
        return "restricted", DENIED[name]
    source, text = licence(name, version)
    if name in WHITELIST:
        return "whitelisted", text
    if PROPRIETARY_OK.match(name):
        return "allowed", text or "NVIDIA proprietary"
    if not text:
        return "unknown", "no licence metadata"
    if source == "expression":
        restricted = restricted_expression(text)
    else:
        restricted = bool(RESTRICTED.search(text))
    return ("restricted" if restricted else "allowed"), text


def main(names):
    extras = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"]["optional-dependencies"]
    names = names or sorted(extras)
    failures = []
    pins_seen = 0
    for extra in names:
        reqs = [r for r in expand(extras, extra) if requirement_name(r) not in SISTERS]
        for python in PYTHONS:
            pins = resolve(reqs, python) if reqs else {}
            pins_seen += len(pins)
            for name, version in sorted(pins.items()):
                kind, text = verdict(name, version)
                if kind in ("restricted", "unknown"):
                    failures.append(f"{extra} (py{python}): {name}=={version} {kind}: {text[:120]}")
                elif kind == "whitelisted":
                    print(f"{extra} (py{python}): {name}=={version} whitelisted: {text[:80]}")
    print(f"extras in: {len(names)}, resolutions: {len(names) * len(PYTHONS)}, "
          f"pins checked: {pins_seen}, failures: {len(failures)}")
    for failure in failures:
        print("FAIL", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
