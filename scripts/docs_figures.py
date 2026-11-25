"""Write the figures of docs/img/ and check the diagram of docs/graph.md.

    python scripts/docs_figures.py           # run each docs/img/plot_*.py
    python scripts/docs_figures.py --check   # exit 1 when a figure or the diagram is out of date

Each ``docs/img/plot_<name>.py`` writes ``<name>.svg`` and ``<name>-dark.svg``
from the repository's own data, with the same bytes for the same data.
``--check`` runs them and fails when an SVG changes. The Mermaid block of
``docs/graph.md`` must list exactly the edges of ``DEFAULT_GRAPH`` with the
diacritics and phonemizers edges.
"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "img"
GRAPH_PAGE = ROOT / "docs" / "graph.md"


def mermaid_edges(page: Path) -> set:
    block = re.search(r"```mermaid\n(.*?)```", page.read_text(encoding="utf-8"), re.S)[1]
    labels = dict(re.findall(r'(\w+)\["([^"]+)"\]', block))
    return {(labels[src], arrow, labels[dst])
            for src, arrow, dst in re.findall(r"^\s*(\w+) (-->|-\.->) (\w+)\s*$", block, re.M)}


def graph_edges() -> set:
    from scriptconv import DEFAULT_GRAPH, diacritics, phonemizers

    graph = DEFAULT_GRAPH.extend(diacritics.register).extend(phonemizers.register)
    return {(e.src, "-->" if e.lossless else "-.->", e.dst) for e in graph.edges}


def main(argv) -> int:
    if argv not in ([], ["--check"]):
        print(__doc__)
        return 2
    status = 0
    before = {path: path.read_bytes() for path in IMG.glob("*.svg")}
    for script in sorted(IMG.glob("plot_*.py")):
        if script.name != "plot_style.py":
            subprocess.run([sys.executable, str(script)], cwd=ROOT, check=True)
    if argv:
        for path in sorted(IMG.glob("*.svg")):
            if before.get(path) != path.read_bytes():
                print(f"{path} is out of date: run python scripts/docs_figures.py")
                status = 1
        shown, real = mermaid_edges(GRAPH_PAGE), graph_edges()
        if shown != real:
            print(f"{GRAPH_PAGE} diagram differs from the graph: only in page {sorted(shown - real)}, "
                  f"only in graph {sorted(real - shown)}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
