"""Check that a README or docs page says what the code does.

    python scripts/check_doc_page.py docs/stack.md

Run it from the repository root. It checks:

- Every python block of the page runs, in order, in one namespace.
- An expression with a ``# value`` comment on its line, or on the line under
  it, gives that value. The value is the comment text before the first double
  space, read by ``ast.literal_eval``.
- An expression with a ``# SomeError: text`` comment raises ``SomeError``, and
  the message holds ``text``.
- A block that starts with ``def``, ``class`` or ``@`` is a stub. Each function
  in it has the parameter names, kinds and defaults of the real function. Each
  enum has the members of the real enum, and each dataclass the field names
  and defaults of the real dataclass.
- Each relative link of the page reaches a file, and each anchor a heading of
  that file.
- README.md: the Extras table names each extra of pyproject.toml, and no other.
- docs/index.md: the numbered list names each page of docs/, in the order
  that the page footers give. The subcommand list is the list of
  ``python -m scriptconv --help``. The links of README.md, AGENTS.md and each
  docs page are checked too.

It does not check prose, the tables not named above, bash blocks, or the
annotations of a stub. It exits 1 at the first mismatch, and 0 otherwise.
"""
import ast
import dataclasses
import enum
import inspect
import re
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fail(message: str):
    print(message)
    sys.exit(1)


def stub_key(obj):
    if not isinstance(obj, type):
        return [(p.name, p.kind, p.default) for p in inspect.signature(obj).parameters.values()]
    if issubclass(obj, enum.Enum):
        return [(member.name, member.value) for member in obj]
    return [(field.name, field.default) for field in dataclasses.fields(obj)]


page = Path(sys.argv[1])
text = page.read_text(encoding="utf-8")
namespace = {}
checked = 0

for block in re.findall(r"```python\n(.*?)```", text, re.S):
    if re.match(r"def |class |@", block):
        source = re.sub(r"\)( -> .+)?$", r")\1: ...", block.strip()) if block.startswith("def") else block
        stubs = dict(namespace)
        exec("from __future__ import annotations\nfrom dataclasses import dataclass\nfrom enum import Enum\n"
             + source, stubs)
        for node in ast.parse(source).body:
            checked += 1
            if stub_key(stubs[node.name]) != stub_key(namespace[node.name]):
                fail(f"{page}: the stub of {node.name} gives {stub_key(stubs[node.name])}, "
                     f"the code gives {stub_key(namespace[node.name])}")
        continue
    lines = block.splitlines()
    for node in ast.parse(block).body:
        comment = None
        if isinstance(node, ast.Expr):
            inline = re.search(r"\s#\s?(.*)$", lines[node.end_lineno - 1])
            below = lines[node.end_lineno] if node.end_lineno < len(lines) else ""
            comment = inline[1] if inline else below[2:] if below.startswith("# ") else None
        if comment is None:
            exec(compile(ast.Module([node], []), str(page), "exec"), namespace)
            continue
        checked += 1
        expected = comment.split("  ")[0].strip()
        code = compile(ast.Expression(node.value), str(page), "eval")
        error = re.match(r"(\w+Error)\b:?\s*(.*)", expected)
        if error:
            try:
                eval(code, namespace)
                raised = None
            except Exception as e:
                raised = e
            if not isinstance(raised, eval(error[1], namespace)) or error[2] not in str(raised):
                fail(f"{page}: {ast.unparse(node)} raises {raised!r}, the page says {expected}")
        elif (value := eval(code, namespace)) != ast.literal_eval(expected):
            fail(f"{page}: {ast.unparse(node)} gives {value!r}, the page says {expected}")

is_index = page.resolve() == ROOT / "docs" / "index.md"
linked = [ROOT / "README.md", ROOT / "AGENTS.md", *sorted((ROOT / "docs").glob("*.md"))] if is_index else [page]
for file in linked:
    body = re.sub(r"<!--.*?-->|```.*?```|`[^`\n]*`", "", file.read_text(encoding="utf-8"), flags=re.S)
    for target in re.findall(r"\]\(([^)\s]+)\)", body):
        if re.match(r"[a-z]+:", target):
            continue
        path, _, anchor = target.partition("#")
        dest = (file.parent / path).resolve() if path else file.resolve()
        if not dest.exists():
            fail(f"{file}: the link {target} reaches no file")
        if not anchor or dest.suffix != ".md":
            continue
        anchors, seen = set(), {}
        for heading in re.findall(r"^#{1,6}\s+(.*?)\s*$", re.sub(r"```.*?```", "", dest.read_text(encoding="utf-8"),
                                                              flags=re.S), re.M):
            heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", re.sub(r"`|\*", "", heading)).strip().lower()
            slug = "".join(c for c in heading if c.isalnum() or c in "-_ ").replace(" ", "-")
            anchors.add(f"{slug}-{seen[slug]}" if slug in seen else slug)
            seen[slug] = seen.get(slug, 0) + 1
        if anchor not in anchors:
            fail(f"{file}: the link {target} names no heading of {dest.name}")

if page.resolve() == ROOT / "docs" / "install.md":
    table = text.split("\n## Extras\n")[1].split("\n## ")[0]
    documented = set(re.findall(r"`([\w-]+)`", " ".join(row.split("|")[1] for row in table.splitlines()
                                                         if row.startswith("| `"))))
    extras = set(tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"])
    if documented != extras:
        fail(f"{page}: the Extras table and pyproject.toml differ in {sorted(documented ^ extras)}")

if is_index:
    docs = ROOT / "docs"
    order = re.findall(r"^\d+\. \*\*\[([\w-]+\.md)\]", text, re.M)
    pages = sorted(p.name for p in docs.glob("*.md") if p.name != "index.md")
    if sorted(order) != pages:
        fail(f"{page}: the list names {sorted(order)}, docs/ holds {pages}")
    for before, after in zip(order, order[1:]):
        if f"→]({after})" not in (docs / before).read_text(encoding="utf-8") or not re.search(
                rf"\[← [^]]*\]\({re.escape(before)}\)", (docs / after).read_text(encoding="utf-8")):
            fail(f"{page}: the footers of {before} and {after} do not link each other")
    usage = subprocess.run([sys.executable, "-m", "scriptconv", "--help"], capture_output=True, text=True).stdout
    commands = re.search(r"\{([\w,]+)\}", usage)[1].split(",")
    listed = re.findall(r"`(\w+)`", re.search(r"subcommands: (.*?)\.\n", text, re.S)[1])
    if listed != commands:
        fail(f"{page}: the page lists the subcommands {listed}, the command line has {commands}")

print(f"OK {page}: {checked} examples and stubs")
