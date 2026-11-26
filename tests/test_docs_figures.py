"""Each figure's data equals a fresh build, and each alt text quotes the numbers of its figure's data."""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_figure_data_matches_a_fresh_build():
    done = subprocess.run([sys.executable, "scripts/docs_figures.py", "--check"], capture_output=True, text=True,
                          cwd=ROOT)
    assert done.returncode == 0, done.stdout + done.stderr


def _alt(page, svg):
    return re.search(rf'<img alt="([^"]*)" src="img/{svg}">', (ROOT / "docs" / page).read_text(encoding="utf-8"))[1]


def _backends_by_extra():
    counts = json.loads((ROOT / "docs" / "img" / "backends-by-extra.json").read_text(encoding="utf-8"))
    total = sum(sum(owners.values()) for _, owners in counts)
    owner = {name: sum(owners.get(name, 0) for _, owners in counts)
             for name in ("scriptconv", "scriptconv-copyleft", "scriptconv-nonfree")}
    split = (f"scriptconv holds {owner['scriptconv']}, scriptconv-copyleft {owner['scriptconv-copyleft']} "
             f"and scriptconv-nonfree {owner['scriptconv-nonfree']}.")
    largest = sorted(counts, key=lambda row: (-sum(row[1].values()), row[0]))[:5]
    named = [f"{extra} {sum(owners.values())}" for extra, owners in largest]
    return total, len(counts), split, f"{', '.join(named[:-1])} and {named[-1]}"


def test_the_index_alt_text_quotes_the_figure_data():
    total, extras, split, _ = _backends_by_extra()
    assert _alt("index.md", "backends-by-extra.svg") == f"{total} phonemizer backends in {extras} extras: {split}"


def test_the_backends_alt_text_quotes_the_figure_data():
    total, extras, split, largest = _backends_by_extra()
    assert _alt("backends.md", "backends-by-extra.svg") == (
        f"{total} backends in {extras} extras: {split} The largest extras are {largest}.")


def test_the_performance_alt_text_quotes_the_figure_data():
    first, second = json.loads((ROOT / "docs" / "img" / "owner-backend-timing.json").read_text(encoding="utf-8"))
    ms = {name: f"{round(first[name]):,} and {round(second[name]):,}" for name in first}
    fastest, *middle, slowest = sorted(first, key=first.get)
    rest = sorted(middle)
    assert _alt("performance.md", "owner-backend-timing.svg") == (
        f"Milliseconds to read 10,000 characters, run 1 and run 2: {fastest} {ms[fastest]}, the fastest; "
        f"{slowest} {ms[slowest]}, the slowest. {', '.join(f'{name} {ms[name]}' for name in rest[:-1])}, "
        f"{rest[-1]} {ms[rest[-1]]}.")
