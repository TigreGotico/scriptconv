"""The scriptconv core imports no third-party module.

A child interpreter refuses every import outside the standard library and this
package, then imports the core modules, the phonemizer contract and the
frontend. A refusal surfaces as a failed import, and the module table is read
afterwards too, so a lazy import that a module runs at import time is seen.
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

CORE = ["scriptconv", "scriptconv.scripts", "scriptconv.notation", "scriptconv.translit",
        "scriptconv.readings", "scriptconv.conventions", "scriptconv.graph",
        "scriptconv.cangjie", "scriptconv.diacritics", "scriptconv.frontend",
        "scriptconv.phonemizers", "scriptconv.phonemizers.base",
        "scriptconv.phonemizers.enums", "scriptconv.phonemizers.registry"]

CHILD = """
import sys

class Refuse:
    def find_spec(self, name, path=None, target=None):
        root = name.split(".")[0]
        if root in sys.stdlib_module_names or root == "scriptconv":
            return None
        raise ImportError(f"third-party import: {name}")

sys.meta_path.insert(0, Refuse())
sys.path.insert(0, sys.argv[1])
for module in sys.argv[2:]:
    __import__(module)
roots = {name.split(".")[0] for name in sys.modules}
print(sorted(r for r in roots
             if r not in sys.stdlib_module_names and r not in ("scriptconv", "__main__")))
"""


def run_child(*modules):
    return subprocess.run([sys.executable, "-I", "-S", "-c", CHILD, str(ROOT), *modules],
                          capture_output=True, text=True, cwd=ROOT)


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
