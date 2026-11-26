"""Print the phonemizer backend table of docs/backends.md from the registry.

    python scripts/backend_table.py           # print the table
    python scripts/backend_table.py --write   # rewrite the table in docs/backends.md
    python scripts/backend_table.py --check   # exit 1 when docs/backends.md differs

The same flags also write or check the leader-language table of
docs/languages.md. ``--write`` and ``--check`` exit 1 and write nothing when a
page lacks one of its two markers.

The rows come from ``Phonemizer`` (enums.py), ``PHONEMIZER_REGISTRY`` and
``LANG_DEFAULTS`` (registry.py), in the order of the enum.
"""
import sys
from pathlib import Path

from scriptconv.phonemizers.base import _primary_subtag
from scriptconv.phonemizers._moved import COPYLEFT, NONFREE
from scriptconv.phonemizers.enums import Phonemizer
from scriptconv.phonemizers.registry import LANG_DEFAULTS, PHONEMIZER_REGISTRY
from scriptconv.scripts import lang_to_script

DOC = Path(__file__).resolve().parent.parent / "docs" / "backends.md"
START = "<!-- backends:start -->"
END = "<!-- backends:end -->"
LANG_DOC = DOC.parent / "languages.md"
LEADERS = ("pt-PT", "pt-BR", "es-CO", "fr-FR", "it-IT", "de-DE", "nl-NL",
           "da-DK", "kab", "hi-IN", "bn-IN", "mwr")
FALLBACK = "none: `orthography2ipa` when it has a spec, else `espeak`"
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


def _extra(member) -> str:
    return PHONEMIZER_REGISTRY[member][2] or "phonemizers"


def language_table() -> str:
    rows = ["| Language | Default backend | Extra | Script | Measured score |",
            "|---|---|---|---|---|"]
    for lang in LEADERS:
        chain = LANG_DEFAULTS.get(_primary_subtag(lang))
        if chain:
            backend = " then ".join(f"`{m.value}`" for m in chain)
        else:
            backend, chain = FALLBACK, (Phonemizer.ORTHOGRAPHY2IPA, Phonemizer.ESPEAK)
        extra = ", ".join(f"`{_extra(m)}`" for m in chain)
        script = lang_to_script(lang)
        rows.append(f"| `{lang}` | {backend} | {extra} | "
                    f"{f'`{script}`' if script else 'not in the map'} | no score in this repo |")
    return "\n".join(rows) + "\n"


def _sync(doc, start, end, body, check) -> int:
    text = doc.read_text(encoding="utf-8")
    if text.count(start + "\n") != 1 or text.count(end) != 1 or text.index(start) > text.index(end):
        print(f"{doc} needs one {start} line and one {end} after it")
        return 1
    head, _, rest = text.partition(start + "\n")
    _, _, tail = rest.partition(end)
    updated = f"{head}{start}\n{body}{end}{tail}"
    if check:
        if updated != text:
            print(f"{doc} is out of date: run python scripts/backend_table.py --write")
            return 1
        return 0
    doc.write_text(updated, encoding="utf-8")
    return 0


def main(argv) -> int:
    if not argv:
        print(table(), end="")
        return 0
    if argv not in (["--check"], ["--write"]):
        print(__doc__)
        return 2
    check = argv == ["--check"]
    return (_sync(DOC, START, END, table(), check)
            or _sync(LANG_DOC, "<!-- languages:start -->", "<!-- languages:end -->",
                     language_table(), check))

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
