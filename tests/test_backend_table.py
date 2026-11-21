"""docs/backends.md holds one row per Phonemizer member, as scripts/backend_table.py writes it."""
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "backend_table.py"


def test_the_backend_table_matches_the_registry():
    result = subprocess.run([sys.executable, str(SCRIPT), "--check"],
                            capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("marker", ["<!-- backends:start -->", "<!-- backends:end -->"])
def test_write_refuses_a_page_without_a_marker(tmp_path, marker):
    spec = importlib.util.spec_from_file_location("backend_table", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    page = tmp_path / "backends.md"
    text = (ROOT / "docs" / "backends.md").read_text(encoding="utf-8").replace(marker, "")
    page.write_text(text, encoding="utf-8")
    script.DOC = page

    assert script.main(["--write"]) == 1
    assert page.read_text(encoding="utf-8") == text
