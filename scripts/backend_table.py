"""Print the phonemizer backend table of docs/backends.md from the registry.

    python scripts/backend_table.py           # print the table
    python scripts/backend_table.py --write   # rewrite the table in docs/backends.md
    python scripts/backend_table.py --check   # exit 1 when docs/backends.md differs

The rows come from ``Phonemizer`` (enums.py), ``PHONEMIZER_REGISTRY`` and
``LANG_DEFAULTS`` (registry.py), in the order of the enum.
"""
import sys
from pathlib import Path

from scriptconv.phonemizers._moved import COPYLEFT, NONFREE
from scriptconv.phonemizers.enums import Phonemizer
from scriptconv.phonemizers.registry import LANG_DEFAULTS, PHONEMIZER_REGISTRY

DOC = Path(__file__).resolve().parent.parent / "docs" / "backends.md"
START = "<!-- backends:start -->"
END = "<!-- backends:end -->"
PACKAGES = {COPYLEFT: "scriptconv-copyleft", NONFREE: "scriptconv-nonfree"}


def table() -> str:
    rows = ["| Backend | Class | Extra | Package | Language default |",
            "|---|---|---|---|---|"]
    for member in Phonemizer:
        module, cls, extra = PHONEMIZER_REGISTRY[member]
        package = next((name for prefix, name in PACKAGES.items()
                        if module.startswith(prefix)), "scriptconv")
        langs = ", ".join(f"`{lang}`" for lang, chain in LANG_DEFAULTS.items()
                          if member in chain)
        rows.append(f"| `{member.value}` | `{cls}` | `{extra or 'phonemizers'}` "
                    f"| {package} | {langs} |")
    return "\n".join(rows) + "\n"


def main(argv) -> int:
    if not argv:
        print(table(), end="")
        return 0
    text = DOC.read_text(encoding="utf-8")
    head, _, rest = text.partition(START + "\n")
    _, _, tail = rest.partition(END)
    updated = f"{head}{START}\n{table()}{END}{tail}"
    if argv == ["--check"]:
        if updated != text:
            print(f"{DOC} is out of date: run python scripts/backend_table.py --write")
            return 1
        return 0
    if argv == ["--write"]:
        DOC.write_text(updated, encoding="utf-8")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
