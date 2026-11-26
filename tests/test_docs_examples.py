"""The docs give the values that the code gives.

Each `>>>` example of the README and of each page in docs/ gives the output that it shows. Each page runs in a fresh
interpreter, because a page shows what a fresh process imports. An example of a backend whose optional package is not
installed is skipped, not failed: the CI test extra does not install every backend. Each figure's data equals a fresh
build, and each alt text quotes the numbers of its figure's data.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PAGES = [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]

_RUN = r'''
import doctest, json, sys
from pathlib import Path

class Runner(doctest.DocTestRunner):
    missing = []

    def report_unexpected_exception(self, out, test, example, exc_info):
        error = exc_info[1]
        if isinstance(error, ImportError) and (error.name or isinstance(error.__cause__, ModuleNotFoundError)):
            self.missing.append(example.source.strip())
            return
        super().report_unexpected_exception(out, test, example, exc_info)

page = Path(sys.argv[1])
test = doctest.DocTestParser().get_doctest(page.read_text(encoding="utf-8"), {}, page.name, str(page), 0)
runner = Runner(optionflags=doctest.ELLIPSIS | doctest.NORMALIZE_WHITESPACE)
report = []
runner.run(test, out=report.append)
print(json.dumps({"examples": len(test.examples), "failures": runner.failures, "missing": runner.missing,
                  "report": "".join(report)}))
'''


@pytest.mark.parametrize("page", PAGES, ids=lambda page: page.relative_to(ROOT).as_posix())
def test_page_examples(page):
    done = subprocess.run([sys.executable, "-c", _RUN, str(page)], capture_output=True, text=True, check=True,
                          cwd=ROOT)
    result = json.loads(done.stdout.splitlines()[-1])
    if not result["examples"]:
        pytest.skip("no examples")
    assert result["failures"] == len(result["missing"]), result["report"]
    if result["missing"] and len(result["missing"]) == result["examples"]:
        pytest.skip(f"every example needs a backend that is not installed: {result['missing'][0]}")


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
