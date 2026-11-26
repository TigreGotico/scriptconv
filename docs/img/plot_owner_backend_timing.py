"""docs/img/owner-backend-timing.svg: the time of five backends to phonemize 10,000 characters.

    python docs/img/plot_owner_backend_timing.py

The values come from scripts/time_owner_backends.txt, the median of each of two runs.
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from plot_style import save  # noqa: E402

TIMING = Path(__file__).resolve().parents[2] / "scripts" / "time_owner_backends.txt"


def runs() -> list[dict[str, float]]:
    blocks = re.split(r"^Run \d+$", TIMING.read_text(encoding="utf-8"), flags=re.M)[1:]
    return [{m[1]: float(m[2]) for m in re.finditer(r"^\| (\w+) \| \w+ \| \w+ \| \d+ \| ([\d.]+) \|", block, re.M)}
            for block in blocks]


def draw(fig, theme, measured):
    names = sorted(measured[0], key=measured[0].get)
    ax = fig.subplots()
    height = 0.38
    for i, (run, colour) in enumerate(zip(measured, theme["series"])):
        ys = [y + (i - 0.5) * height for y in range(len(names))]
        ax.barh(ys, [run[n] for n in names], height=height, color=colour, label=f"run {i + 1}")
        for y, name in zip(ys, names):
            ax.text(run[name] * 1.08, y, f"{run[name]:,.0f} ms", va="center", color=theme["text"], fontsize=9)
    ax.set_yticks(range(len(names)), names)
    ax.set_xscale("log")
    ax.set_xlim(10, 40000)
    ax.set_xticks([10, 100, 1000, 10000], ["10", "100", "1,000", "10,000"])
    ax.invert_yaxis()
    ax.set_xlabel("Median ms for one read of 10,000 characters (log scale)")
    ax.grid(axis="y", visible=False)
    ax.set_title("Time to phonemize 10,000 characters")
    ax.legend(loc="upper right")


if __name__ == "__main__":
    save("docs/img/owner-backend-timing", draw, runs())
