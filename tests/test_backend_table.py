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


def test_the_language_table_matches_the_registry(tmp_path):
    spec = importlib.util.spec_from_file_location("backend_table", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    text = (ROOT / "docs" / "languages.md").read_text(encoding="utf-8")
    assert "| `pt-PT` | `tugaphone` | `pt-phonemizers` | `Latn` |" in text
    page = tmp_path / "languages.md"
    page.write_text(text, encoding="utf-8")
    script.LANG_DOC = page

    assert script.main(["--check"]) == 0
    assert script.main(["--write"]) == 0
    assert page.read_text(encoding="utf-8") == text


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


def test_each_leader_row_names_the_backend_that_phonemizer_for_lang_returns():
    from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY, phonemizer_for_lang
    by_class = {cls: member for member, (_, cls, _) in PHONEMIZER_REGISTRY.items()}
    rows = {row.split("|")[1].strip(" `"): row.split("|")[2]
            for row in (ROOT / "docs" / "languages.md").read_text(encoding="utf-8").splitlines()
            if row.startswith("| `")}
    assert len(rows) == 12
    for lang, cell in rows.items():
        member = by_class[type(phonemizer_for_lang(lang)).__name__]
        assert f"`{member.value}`" in cell, (lang, cell)
    assert "unsupported" in rows["mwr"]
