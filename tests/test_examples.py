"""Smoke-tests: run every examples/ script via subprocess and assert exit 0 + non-empty stdout."""
import subprocess
import sys
from pathlib import Path

EXAMPLES_DIR = Path(__file__).parent.parent / "examples"

EXAMPLE_SCRIPTS = sorted(EXAMPLES_DIR.glob("[0-9]*.py"))


def _run(script: Path):
    result = subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
    )
    return result


def test_examples_exist():
    assert len(EXAMPLE_SCRIPTS) >= 11, (
        f"Expected at least 11 example scripts, found {len(EXAMPLE_SCRIPTS)}"
    )


def test_01_detect_script():
    r = _run(EXAMPLES_DIR / "01_detect_script.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_02_lang_to_script():
    r = _run(EXAMPLES_DIR / "02_lang_to_script.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_03_arpabet_roundtrip():
    r = _run(EXAMPLES_DIR / "03_arpabet_roundtrip.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_04_xsampa():
    r = _run(EXAMPLES_DIR / "04_xsampa.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_05_buckwalter():
    r = _run(EXAMPLES_DIR / "05_buckwalter.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_06_lexique():
    r = _run(EXAMPLES_DIR / "06_lexique.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_07_hangul_decompose():
    r = _run(EXAMPLES_DIR / "07_hangul_decompose.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_08_script_distribution():
    r = _run(EXAMPLES_DIR / "08_script_distribution.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_09_script_to_langs():
    r = _run(EXAMPLES_DIR / "09_script_to_langs.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_10_new_labels():
    r = _run(EXAMPLES_DIR / "10_new_labels.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_11_cli():
    r = _run(EXAMPLES_DIR / "11_cli.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_12_kirshenbaum():
    r = _run(EXAMPLES_DIR / "12_kirshenbaum.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_13_script_runs():
    r = _run(EXAMPLES_DIR / "13_script_runs.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_14_kana_transliteration():
    r = _run(EXAMPLES_DIR / "14_kana_transliteration.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_15_cotovia():
    r = _run(EXAMPLES_DIR / "15_cotovia.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()


def test_16_rfe():
    r = _run(EXAMPLES_DIR / "16_rfe.py")
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip()
