"""Write the figures of docs/ from the repository's own data.

    python scripts/docs_figures.py           # write docs/figures/*.svg
    python scripts/docs_figures.py --check   # exit 1 when a figure or a diagram is out of date

Inputs:

- ``PHONEMIZER_REGISTRY`` and ``scriptconv.phonemizers._moved``: the backends
  of each extra and the package that holds each wrapper.
  Output: ``docs/figures/backends-by-extra.svg``.
- ``scripts/time_owner_backends.txt``: the two timing runs of five backends.
  Output: ``docs/figures/owner-backend-timing.svg``.
- ``DEFAULT_GRAPH`` with the diacritics and phonemizers edges: the Mermaid
  block of ``docs/graph.md`` must list exactly these edges. ``--check`` reads
  it; the script writes no file for it.

The SVG files hold no timestamp, so two runs write the same bytes.
"""
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIGURES = ROOT / "docs" / "figures"
TIMING = ROOT / "scripts" / "time_owner_backends.txt"
GRAPH_PAGE = ROOT / "docs" / "graph.md"

TEXT = "#808080"
GRID = "#80808055"
COLOURS = ["#4C8DD6", "#E0883A", "#A66CC9"]
FONT = 'font-family="sans-serif" font-size="15"'


def svg(width: int, height: int, title: str, description: str, body: list) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="{width}" '
            f'height="{height}" role="img" aria-labelledby="t d">\n<title id="t">{title}</title>\n'
            f'<desc id="d">{description}</desc>\n' + "\n".join(body) + "\n</svg>\n")


def text(x, y, content, anchor="start", fill=TEXT) -> str:
    return f'<text x="{x}" y="{y}" text-anchor="{anchor}" fill="{fill}" {FONT}>{content}</text>'


def backends_by_extra() -> str:
    from scriptconv.phonemizers._moved import COPYLEFT, NONFREE
    from scriptconv.phonemizers.enums import Phonemizer
    from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY

    packages = [("scriptconv", None), ("scriptconv-copyleft", COPYLEFT), ("scriptconv-nonfree", NONFREE)]
    counts: dict = {}
    for member in Phonemizer:
        module, _, extra = PHONEMIZER_REGISTRY[member]
        index = next((i for i, (_, prefix) in enumerate(packages) if prefix and module.startswith(prefix)), 0)
        counts.setdefault(extra or "phonemizers", Counter())[index] += 1
    rows = sorted(counts.items(), key=lambda item: (-sum(item[1].values()), item[0]))
    total = sum(sum(c.values()) for c in counts.values())
    per_package = [sum(c[i] for c in counts.values()) for i in range(3)]

    left, unit, top, row = 190, 52, 52, 26
    height = top + row * len(rows) + 16
    body = []
    for i, (name, colour) in enumerate(zip((p for p, _ in packages), COLOURS)):
        x = 16 + i * 215
        body.append(f'<rect x="{x}" y="14" width="16" height="16" fill="{colour}"/>')
        body.append(text(x + 24, 28, f"{name} ({per_package[i]})"))
    for step in range(0, 8):
        x = left + step * unit
        body.append(f'<line x1="{x}" y1="{top - 8}" x2="{x}" y2="{height - 12}" stroke="{GRID}"/>')
        body.append(text(x, height + 2, str(step), "middle"))
    for r, (extra, by_package) in enumerate(rows):
        y = top + r * row
        body.append(text(left - 10, y + 17, extra, "end"))
        x = left
        for i in range(3):
            if by_package[i]:
                body.append(f'<rect x="{x}" y="{y}" width="{by_package[i] * unit}" height="20" '
                            f'fill="{COLOURS[i]}"/>')
                x += by_package[i] * unit
        body.append(text(x + 8, y + 17, str(sum(by_package.values()))))
    sizes = ", ".join(f"{extra} {sum(c.values())}" for extra, c in rows[:5])
    return svg(720, height + 10, "Phonemizer backends by extra and package",
               f"{total} backends in {len(rows)} extras. By package: scriptconv {per_package[0]}, "
               f"scriptconv-copyleft {per_package[1]}, scriptconv-nonfree {per_package[2]}. "
               f"The largest extras are {sizes}.", body)


def owner_backend_timing() -> str:
    import math

    runs = []
    for block in re.split(r"^Run \d+$", TIMING.read_text(encoding="utf-8"), flags=re.M)[1:]:
        runs.append({m[1]: float(m[2]) for m in
                     re.finditer(r"^\| (\w+) \| \w+ \| \w+ \| \d+ \| ([\d.]+) \|", block, re.M)})
    names = sorted(runs[0], key=lambda n: runs[0][n])
    left, width, top, row = 130, 540, 52, 56
    low, high = 1, 4.3          # log10 of the axis ends in ms: 10 to 20,000
    height = top + row * len(names) + 20

    def x(ms):
        return left + (math.log10(ms) - low) / (high - low) * width

    body = []
    for i, label in enumerate(("run 1", "run 2")):
        body.append(f'<rect x="{16 + i * 110}" y="14" width="16" height="16" fill="{COLOURS[i]}"/>')
        body.append(text(16 + i * 110 + 24, 28, label))
    for tick in (10, 100, 1000, 10000):
        body.append(f'<line x1="{x(tick):.1f}" y1="{top - 8}" x2="{x(tick):.1f}" y2="{height - 20}" stroke="{GRID}"/>')
        body.append(text(f"{x(tick):.1f}", height - 2, f"{tick:,} ms", "middle"))
    for r, name in enumerate(names):
        y = top + r * row
        body.append(text(left - 10, y + 30, name, "end"))
        for i, run in enumerate(runs):
            ms = run[name]
            w = x(ms) - left
            body.append(f'<rect x="{left}" y="{y + i * 24}" width="{w:.1f}" height="20" fill="{COLOURS[i]}"/>')
            body.append(text(f"{left + w + 8:.1f}", y + i * 24 + 16, f"{ms:,.0f} ms"))
    values = "; ".join(f"{n} {runs[0][n]:,.0f} and {runs[1][n]:,.0f} ms" for n in names)
    return svg(720, height, "Time to phonemize 10,000 characters",
               f"Median milliseconds for one read of about 10,000 characters of prose, in two runs, "
               f"on a log scale: {values}.", body)


def mermaid_edges(page: Path) -> set:
    block = re.search(r"```mermaid\n(.*?)```", page.read_text(encoding="utf-8"), re.S)[1]
    labels = dict(re.findall(r'(\w+)\["([^"]+)"\]', block))
    return {(labels[src], arrow, labels[dst])
            for src, arrow, dst in re.findall(r"^\s*(\w+) (-->|-\.->) (\w+)\s*$", block, re.M)}


def graph_edges() -> set:
    from scriptconv import DEFAULT_GRAPH, diacritics, phonemizers

    graph = DEFAULT_GRAPH.extend(diacritics.register).extend(phonemizers.register)
    return {(e.src, "-->" if e.lossless else "-.->", e.dst) for e in graph.edges}


FIGURE_FILES = {"backends-by-extra.svg": backends_by_extra, "owner-backend-timing.svg": owner_backend_timing}


def main(argv) -> int:
    if argv not in ([], ["--check"]):
        print(__doc__)
        return 2
    status = 0
    for name, make in FIGURE_FILES.items():
        path = FIGURES / name
        fresh = make()
        if argv:
            if not path.exists() or path.read_text(encoding="utf-8") != fresh:
                print(f"{path} is out of date: run python scripts/docs_figures.py")
                status = 1
        else:
            FIGURES.mkdir(exist_ok=True)
            path.write_text(fresh, encoding="utf-8")
    if argv:
        shown, real = mermaid_edges(GRAPH_PAGE), graph_edges()
        if shown != real:
            print(f"{GRAPH_PAGE} diagram differs from the graph: only in page {sorted(shown - real)}, "
                  f"only in graph {sorted(real - shown)}")
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
