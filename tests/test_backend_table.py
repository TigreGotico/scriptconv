"""docs/backends.md holds one row per Phonemizer member, as scripts/backend_table.py writes it."""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_backend_table_matches_the_registry():
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "backend_table.py"), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
