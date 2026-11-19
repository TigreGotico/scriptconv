"""The scriptconv core imports no third-party module.

A child interpreter records and refuses every import outside the standard
library and this package, then imports the core modules, the phonemizer
contract and the frontend. It prints each third-party name that was tried, so
an import inside ``try`` that catches the refusal is seen too. The module
table is read afterwards as well.
"""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

CORE = ["scriptconv", "scriptconv.scripts", "scriptconv.notation", "scriptconv.translit",
        "scriptconv.readings", "scriptconv.conventions", "scriptconv.graph",
        "scriptconv.cangjie", "scriptconv.diacritics", "scriptconv.frontend",
        "scriptconv.phonemizers", "scriptconv.phonemizers.base",
        "scriptconv.phonemizers.enums", "scriptconv.phonemizers.registry"]

CHILD = """
import builtins
import sys

own = {module.split(".")[0] for module in sys.argv[2:]}
allowed = set(sys.stdlib_module_names) | own | {"__main__"}
tried = set()
# The name in each import statement that is running. A finder sees only
# "org" for "import org.x", so the full name comes from here.
statements = []
import_statement = builtins.__import__

def record(name, *args, **kwargs):
    statements.append(name)
    try:
        return import_statement(name, *args, **kwargs)
    finally:
        statements.pop()

class Refuse:
    def find_spec(self, name, path=None, target=None):
        root = name.split(".")[0]
        if root in allowed:
            return None
        # copy tries the Jython module org.python.core inside try, on Python 3.11.
        if statements and statements[-1] == "org.python.core":
            return None
        tried.add(root)
        raise ImportError(f"third-party import: {name}")

builtins.__import__ = record
sys.meta_path.insert(0, Refuse())
sys.path.insert(0, sys.argv[1])
for module in sys.argv[2:]:
    __import__(module)
roots = {name.split(".")[0] for name in sys.modules} | tried
print(sorted(roots - allowed))
"""


def run_child(*modules, root=ROOT):
    return subprocess.run([sys.executable, "-I", "-S", "-c", CHILD, str(root), *modules],
                          capture_output=True, text=True, cwd=root)


def test_the_core_imports_only_the_standard_library():
    result = run_child(*CORE)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[]"


def test_the_refusal_catches_a_third_party_import():
    # quebra_frases is a real dependency of the phonemizer extras, so this
    # fails if the child stops refusing.
    result = run_child("scriptconv.phonemizers.ru")
    assert result.returncode != 0
    assert "third-party import: quebra_frases" in result.stderr


@pytest.mark.parametrize("statement, seen", [
    ("import langcodes", "['langcodes']"),
    ("import org.example", "['org']"),
    ("from org.python import core", "['org']"),
    ("from org.python.core import PyStringMap", "[]"),
])
def test_the_guard_sees_an_import_that_catches_the_refusal(tmp_path, statement, seen):
    (tmp_path / "guarded.py").write_text(f"try:\n    {statement}\nexcept ImportError:\n    pass\n")
    result = run_child("guarded", root=tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == seen
