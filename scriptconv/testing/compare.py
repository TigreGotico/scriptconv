"""The sentence gate: score a frontend and each of its stages against orthography2ipa.

A downstream stage stays only when it makes the result better than standalone
orthography2ipa. This module measures that, one stage at a time.

A sentence set is a TSV file with this header row::

    id  lang  category  text  expected_ipa  source  tier

``category`` is one of :data:`CATEGORIES` and ``tier`` is ``gold`` or
``silver``. The two tiers are always scored apart: :func:`per_by_category`
refuses rows from more than one tier.

The phoneme error rate (PER) of a category is the edit distance between the
backend output and ``expected_ipa``, summed over the rows of the category,
divided by the summed segment count of ``expected_ipa``. Segments come from
``orthography2ipa.allophony.segment_ipa``. Whitespace, syllable marks,
prosodic boundaries and tie bars are not segments, so ``t͡s`` scores as ``ts``.
A stress mark is one segment, because stress placement changes what a voice
says. A row whose ``expected_ipa`` has no segments is skipped with a warning.

The gain of one system over another is the error it removes in a category,
divided by the segment count of the category. The noise is the largest error
change in one row of the category, divided by the same count. A stage passes
when its gain in its own category is larger than the noise, so more than one
sentence carries it. In every other category it may lose one segment at most.

A backend is any object with ``phonemize(text, lang) -> list[list[str]]``, as
every scriptconv phonemizer has. A backend that can switch a stage off also has
``without(stage)``, see :class:`Ablatable`. For a backend without it, the gate
reports the stage as not ablatable. The gate fails when a gold stage has no
verdict.

Command line::

    python -m scriptconv.testing.compare --lang pt-PT \\
        --tsv tests/data/sentences/pt-PT.tsv --backend tugaphone \\
        --stages homographs:homograph,numbers:number
"""
from __future__ import annotations

import argparse
import csv
import importlib
import re
import sys
import unicodedata
import warnings
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Protocol, Sequence, runtime_checkable

CATEGORIES = ("plain", "number", "date", "abbreviation", "homograph", "contact")
TIERS = ("gold", "silver")
COLUMNS = ("id", "lang", "category", "text", "expected_ipa", "source", "tier")

# Syllable boundaries, linking marks, prosodic group boundaries and the tie
# bars above (U+0361) and below (U+035C).
_NOT_SEGMENTS = str.maketrans("", "", ".‿|‖\u0361\u035c")
# Skip reasons that are defects in the sentence set, not filters.
DEFECTS = ("column count", "unknown category", "unknown tier", "empty text or expected_ipa", "duplicate id",
           "duplicate text")
_STRESS = re.compile("([ˈˌ])")


@dataclass(frozen=True)
class Row:
    id: str
    lang: str
    category: str
    text: str
    expected_ipa: str
    source: str
    tier: str


@runtime_checkable
class Backend(Protocol):
    def phonemize(self, text: str, lang: str) -> list[list[str]]: ...


@runtime_checkable
class Ablatable(Backend, Protocol):
    def without(self, stage: str) -> Backend:
        """The same backend with *stage* switched off.

        Raises ``ValueError`` for a stage the backend does not have.
        """


@dataclass(frozen=True)
class Comparison:
    """Two systems on the same rows, per category.

    ``gain`` is the error that the second system removes, divided by the
    reference segment count of the category. A positive gain is good.
    ``noise`` is the largest error change in one row, divided by the same count.
    ``segments`` is that reference segment count.
    """
    gain: dict[str, float]
    noise: dict[str, float]
    segments: dict[str, int]


# A comparison for each key: "full_vs_o2i" and one key per stage.
# A stage of a backend that is not ablatable maps to None.
Report = dict[str, Optional[Comparison]]


def read_tsv(path: str, lang: str) -> tuple[list[Row], Counter]:
    """The rows of *path* for *lang*, and the count of skipped rows by reason.

    A row with the id or the text of an earlier row is a duplicate. A repeated
    sentence would count as many sentences and loosen the noise of its category.
    """
    rows: list[Row] = []
    skipped: Counter = Counter()
    ids: set[str] = set()
    texts: set[str] = set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE)
        header = tuple(next(reader, ()))
        if header != COLUMNS:
            raise ValueError(f"{path}: header must be {' '.join(COLUMNS)}, got {' '.join(header)}")
        for fields in reader:
            if len(fields) != len(COLUMNS):
                skipped["column count"] += 1
                continue
            row = Row(*(field.strip() for field in fields))
            if row.lang != lang:
                skipped["other lang"] += 1
            elif row.category not in CATEGORIES:
                skipped["unknown category"] += 1
            elif row.tier not in TIERS:
                skipped["unknown tier"] += 1
            elif not row.text or not segments(row.expected_ipa):
                skipped["empty text or expected_ipa"] += 1
            elif row.id in ids:
                skipped["duplicate id"] += 1
            elif row.text in texts:
                skipped["duplicate text"] += 1
            else:
                ids.add(row.id)
                texts.add(row.text)
                rows.append(row)
    return rows, skipped


def segments(ipa: str) -> list[str]:
    """The phoneme segments of *ipa* that the PER counts."""
    from orthography2ipa.allophony import segment_ipa

    out: list[str] = []
    for word in unicodedata.normalize("NFC", ipa).translate(_NOT_SEGMENTS).split():
        for part in _STRESS.split(word):
            if part in ("ˈ", "ˌ"):
                out.append(part)
            elif part:
                out.extend(segment_ipa(part))
    return out


def edit_distance(ref: Sequence[str], hyp: Sequence[str]) -> int:
    """Levenshtein distance between two segment sequences, unit costs."""
    prev = list(range(len(hyp) + 1))
    for i, r in enumerate(ref, 1):
        curr = [i]
        for j, h in enumerate(hyp, 1):
            curr.append(min(prev[j] + 1, curr[j - 1] + 1, prev[j - 1] + (r != h)))
        prev = curr
    return prev[-1]


def phonemes(backend: Backend, text: str, lang: str) -> str:
    """The backend output for *text* as one IPA string, sentences joined by a space."""
    return " ".join("".join(sentence) for sentence in backend.phonemize(text, lang))


def _references(rows: Iterable[Row]) -> list[tuple[Row, list[str]]]:
    """Each row with the segments of its reference. The rows must share one
    tier. A row whose reference has no segments is skipped with a warning."""
    rows = list(rows)
    tiers = {row.tier for row in rows}
    if len(tiers) > 1:
        raise ValueError(f"rows mix tiers {sorted(tiers)}; score each tier apart")
    references = []
    for row in rows:
        ref = segments(row.expected_ipa)
        if ref:
            references.append((row, ref))
        else:
            warnings.warn(f"row {row.id}: expected_ipa {row.expected_ipa!r} has no segments, skipped",
                          stacklevel=3)
    return references


def _errors(references: Sequence[tuple[Row, list[str]]], backend: Backend) -> list[int]:
    return [edit_distance(ref, segments(phonemes(backend, row.text, row.lang)))
            for row, ref in references]


def per_by_category(rows: Iterable[Row], backend: Backend) -> dict[str, float]:
    """PER of *backend* on *rows*, per category. The rows must share one tier."""
    references = _references(rows)
    errors: Counter = Counter()
    length: Counter = Counter()
    for (row, ref), row_errors in zip(references, _errors(references, backend)):
        errors[row.category] += row_errors
        length[row.category] += len(ref)
    return {category: errors[category] / length[category] for category in length}


def _compare(references: Sequence[tuple[Row, list[str]]],
             before: Sequence[int], after: Sequence[int]) -> Comparison:
    length: Counter = Counter()
    removed: Counter = Counter()
    largest: Counter = Counter()
    for (row, ref), b, a in zip(references, before, after):
        length[row.category] += len(ref)
        removed[row.category] += b - a
        largest[row.category] = max(largest[row.category], abs(b - a))
    return Comparison(gain={c: removed[c] / n for c, n in length.items()},
                      noise={c: largest[c] / n for c, n in length.items()},
                      segments=dict(length))


def compare_backends(rows: Iterable[Row], before: Backend, after: Backend) -> Comparison:
    """The gain of *after* over *before* on *rows*, and its noise, per category."""
    references = _references(rows)
    return _compare(references, _errors(references, before), _errors(references, after))


def stage_gain(rows: Sequence[Row], backend: Backend, stages: Iterable[str],
               baseline: Optional[Backend] = None) -> Report:
    """Gain is error removed, so a positive number is good. PER falls as quality rises.

    ``full_vs_o2i`` compares *baseline*, which is standalone orthography2ipa
    unless given, with *backend*. Each stage compares the backend without that
    stage with *backend*, or maps to ``None`` when *backend* is not
    :class:`Ablatable`.
    """
    if baseline is None:
        from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
        baseline = Orthography2IPAPhonemizer()
    references = _references(rows)
    full = _errors(references, backend)
    report: Report = {"full_vs_o2i": _compare(references, _errors(references, baseline), full)}
    for stage in stages:
        if isinstance(backend, Ablatable):
            report[stage] = _compare(references, _errors(references, backend.without(stage)), full)
        else:
            report[stage] = None
    return report


def verdict(report: Report, stage: str, own_category: str) -> Optional[bool]:
    """True when *stage* gains more than its noise in its own category and
    loses no more than one segment in any other. ``None`` when the stage is
    not ablatable.

    A gain that one row carries equals the noise, so it does not pass. An
    ablation is deterministic, so a loss of more than one segment in another
    category is real harm, however the loss is spread over the rows.
    """
    comparison = report[stage]
    if comparison is None:
        return None
    return comparison.gain[own_category] > comparison.noise[own_category] and all(
        gain >= -1 / comparison.segments[category]
        for category, gain in comparison.gain.items() if category != own_category)


def _load_backend(name: str) -> Backend:
    """A scriptconv phonemizer name, or ``module:attribute`` for a backend,
    a backend class or a factory that takes no arguments."""
    if ":" in name:
        module, attribute = name.split(":", 1)
        try:
            obj = getattr(importlib.import_module(module), attribute)
        except AttributeError:
            raise ImportError(f"backend {name!r}: module {module!r} has no attribute {attribute!r}") from None
        return obj() if isinstance(obj, type) or not isinstance(obj, Backend) else obj
    from scriptconv.phonemizers import Phonemizer, get_phonemizer
    return get_phonemizer(Phonemizer(name))


def _parse_stages(spec: str) -> list[tuple[str, str]]:
    """``name[:category]`` pairs. A name that is a category is its own category."""
    stages = []
    for item in filter(None, (part.strip() for part in spec.split(","))):
        name, _, category = item.partition(":")
        category = category or name
        if category not in CATEGORIES:
            raise ValueError(f"stage {name!r}: give its category as {name}:<one of {', '.join(CATEGORIES)}>")
        stages.append((name, category))
    return stages


def _signed(categories: Mapping[str, float]) -> str:
    return "  ".join(f"{category} {value:+.4f}" for category, value in categories.items())


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m scriptconv.testing.compare",
        description="Score a backend and each of its stages against orthography2ipa.")
    parser.add_argument("--lang", required=True, help="language code of the rows to score")
    parser.add_argument("--tsv", required=True, help="sentence set: id lang category text expected_ipa source tier")
    parser.add_argument("--backend", required=True,
                        help="scriptconv phonemizer name, or module:attribute")
    parser.add_argument("--stages", default="", help="comma list of stage[:own category]")
    parser.add_argument("--allow-skips", action="store_true",
                        help=f"score the set when rows are skipped for: {', '.join(DEFECTS)}")
    args = parser.parse_args(argv)
    try:
        stages = _parse_stages(args.stages)
        rows, skipped = read_tsv(args.tsv, args.lang)
        backend = _load_backend(args.backend)
        if isinstance(backend, Ablatable):
            for name, _ in stages:
                backend.without(name)
    except (OSError, ValueError, ImportError) as e:
        parser.error(str(e))

    reasons = ", ".join(f"{reason} {n}" for reason, n in sorted(skipped.items()))
    print(f"rows: read {len(rows) + sum(skipped.values())}, scored {len(rows)}, "
          f"skipped {sum(skipped.values())}" + (f" ({reasons})" if reasons else ""))
    defects = sum(skipped[reason] for reason in DEFECTS)
    if defects and not args.allow_skips:
        print(f"gate: FAIL  {defects} skipped for a defect; fix the rows or pass --allow-skips")
        return 1
    if not rows:
        print("gate: FAIL  no row is scored")
        return 1

    failures = [] if stages else ["no stage given, use --stages"]
    for tier in TIERS:
        tier_rows = [row for row in rows if row.tier == tier]
        if not tier_rows:
            print(f"{tier}: no rows, no verdict")
            if tier == "gold":
                failures.append("no gold rows")
            continue
        counts = Counter(row.category for row in tier_rows)
        print(f"{tier}: rows " + "  ".join(f"{c} {n}" for c, n in counts.items()))
        report = stage_gain(tier_rows, backend, [name for name, _ in stages])
        full_vs_o2i = report["full_vs_o2i"].gain
        print(f"{tier}: full_vs_o2i  {_signed(full_vs_o2i)}")
        if tier == "gold":
            failures += [f"full_vs_o2i {c} {gain:+.4f}, the backend is worse than orthography2ipa"
                         for c, gain in full_vs_o2i.items() if gain < 0]
        for name, own in stages:
            comparison = report[name]
            if comparison is None:
                print(f"{tier}: {name}  not ablatable")
                failure = f"{name} not ablatable"
            elif own not in comparison.gain:
                print(f"{tier}: {name}  no {own} rows, no verdict")
                failure = f"{name} has no {own} rows"
            else:
                passed = verdict(report, name, own)
                print(f"{tier}: {name}  {'PASS' if passed else 'FAIL'}  own {own} "
                      f"{comparison.gain[own]:+.4f} (noise {comparison.noise[own]:.4f})  "
                      f"{_signed(comparison.gain)}")
                failure = None if passed else f"{name} FAIL"
            if tier == "gold" and failure:
                failures.append(failure)
    print(f"gate: FAIL  {'; '.join(failures)}" if failures else "gate: PASS")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
