"""Each README and docs page with an agent hint says what the code does, as scripts/check_doc_page.py checks it."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted(path.relative_to(ROOT).as_posix() for path in [ROOT / "README.md", *(ROOT / "docs").glob("*.md")]
               if "<!-- agent-hint" in path.read_text(encoding="utf-8"))


def test_the_readme_and_the_index_are_among_the_checked_pages():
    assert {"README.md", "docs/index.md"} <= set(PAGES)


@pytest.mark.parametrize("page", PAGES)
def test_the_page_matches_the_code(page):
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / "check_doc_page.py"), page],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
