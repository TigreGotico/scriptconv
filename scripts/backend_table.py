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

from scriptconv.phonemizers._moved import COPYLEFT, NONFREE
from scriptconv.phonemizers.enums import Phonemizer
from scriptconv.phonemizers.registry import LANG_DEFAULTS, PHONEMIZER_REGISTRY
from scriptconv.scripts import lang_to_script

DOC = Path(__file__).resolve().parent.parent / "docs" / "backends.md"
START = "<!-- backends:start -->"
END = "<!-- backends:end -->"
LANG_DOC = DOC.parent / "languages.md"
# leader tag -> a native word; a backend that returns no phonemes for it is "unsupported"
LEADERS = {"pt-PT": "casa", "pt-BR": "casa", "es-CO": "casa", "fr-FR": "maison",
           "it-IT": "casa", "de-DE": "Haus", "nl-NL": "huis", "da-DK": "hus",
           "kab": "azul", "hi-IN": "नमस्ते", "bn-IN": "নমস্কার", "mwr": "राम"}
SCORES = {"tugaphone": "[tugaphone scoreboard]"
          "(https://github.com/TigreGotico/tugaphone/blob/dev/docs/benchmarking.md)"}
NOTES = {"kab": " ([#494](https://github.com/TigreGotico/scriptconv/issues/494))"}
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
    """Rows from the backend that ``phonemizer_for_lang`` returns in this environment."""
    from scriptconv.phonemizers.registry import phonemizer_for_lang
    by_class = {cls: member for member, (_, cls, _) in PHONEMIZER_REGISTRY.items()}
    rows = ["| Language | Default backend | Extra | Script | Measured score |",
            "|---|---|---|---|---|"]
    for lang, word in LEADERS.items():
        backend = phonemizer_for_lang(lang)
        member = by_class[type(backend).__name__]
        script = lang_to_script(lang)
        script = f"`{script}`" if script else "not in the map" + NOTES.get(lang, "")
        if backend.phonemize_string(word, lang).strip():
            rows.append(f"| `{lang}` | `{member.value}` | `{_extra(member)}` | {script} "
                        f"| {SCORES.get(member.value, 'none')} |")
        else:
            rows.append(f"| `{lang}` | unsupported: `{member.value}` returns no phonemes "
                        f"| `{_extra(member)}` | {script} | none |")
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
