"""docs/img/backends-by-extra.svg: the phonemizer backends of each extra, by the package that holds them.

    python docs/img/plot_backends_by_extra.py

The counts come from PHONEMIZER_REGISTRY and scriptconv.phonemizers._moved.
"""
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from plot_style import save  # noqa: E402

from scriptconv.phonemizers._moved import COPYLEFT, NONFREE  # noqa: E402
from scriptconv.phonemizers.enums import Phonemizer  # noqa: E402
from scriptconv.phonemizers.registry import PHONEMIZER_REGISTRY  # noqa: E402

PACKAGES = [("scriptconv", None), ("scriptconv-copyleft", COPYLEFT), ("scriptconv-nonfree", NONFREE)]


def counts() -> list[list]:
    by_extra: dict[str, Counter] = {}
    for member in Phonemizer:
        module, _, extra = PHONEMIZER_REGISTRY[member]
        package = next((name for name, prefix in PACKAGES if prefix and module.startswith(prefix)), "scriptconv")
        by_extra.setdefault(extra or "phonemizers", Counter())[package] += 1
    rows = sorted(by_extra.items(), key=lambda item: (sum(item[1].values()), item[0]))
    return [[extra, dict(sorted(by_package.items()))] for extra, by_package in rows]


def draw(fig, theme, rows):
    ax = fig.subplots()
    names = [extra for extra, _ in rows]
    left = [0] * len(rows)
    for (package, _), colour in zip(PACKAGES, theme["series"]):
        values = [by_package.get(package, 0) for _, by_package in rows]
        total = sum(values)
        ax.barh(names, values, left=left, color=colour, label=f"{package} ({total})", height=0.7)
        left = [a + b for a, b in zip(left, values)]
    for y, width in enumerate(left):
        ax.text(width + 0.1, y, str(width), va="center", color=theme["text"], fontsize=9)
    ax.set_xlabel("Backends")
    ax.grid(axis="y", visible=False)
    ax.set_title(f"{sum(left)} phonemizer backends in {len(rows)} extras")
    ax.legend(loc="lower right")


if __name__ == "__main__":
    save("docs/img/backends-by-extra", draw, counts(), height=6.4)
