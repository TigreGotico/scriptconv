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
``orthography2ipa.allophony.segment_ipa``. Whitespace, syllable marks and
prosodic boundaries are not segments. A stress mark is one segment, because
stress placement changes what a voice says.

A backend is any object with ``phonemize(text, lang) -> list[list[str]]``, as
every scriptconv phonemizer has. A backend that can switch a stage off also has
``without(stage)``, see :class:`Ablatable`. For a backend without it, the gate
reports the stage as not ablatable and gives no verdict.

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
from collections import Counter
from dataclasses import dataclass
from typing import Iterable, Mapping, Optional, Protocol, Sequence, runtime_checkable

CATEGORIES = ("plain", "number", "date", "abbreviation", "homograph", "contact")
TIERS = ("gold", "silver")
COLUMNS = ("id", "lang", "category", "text", "expected_ipa", "source", "tier")

# Syllable boundaries, linking marks and prosodic group boundaries.
_NOT_SEGMENTS = str.maketrans("", "", ".‿|‖")
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


# Gain per category for each key: "full_vs_o2i" and one key per stage.
# A stage of a backend that is not ablatable maps to None.
Report = dict[str, Optional[dict[str, float]]]


def read_tsv(path: str, lang: str) -> tuple[list[Row], Counter]:
    """The rows of *path* for *lang*, and the count of skipped rows by reason."""
    rows: list[Row] = []
    skipped: Counter = Counter()
    with open(path, encoding="utf-8", newline="") as f:
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
            else:
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


def per_by_category(rows: Iterable[Row], backend: Backend) -> dict[str, float]:
    """PER of *backend* on *rows*, per category. The rows must share one tier."""
    rows = list(rows)
    tiers = {row.tier for row in rows}
    if len(tiers) > 1:
        raise ValueError(f"rows mix tiers {sorted(tiers)}; score each tier apart")
    errors: Counter = Counter()
    length: Counter = Counter()
    for row in rows:
        ref = segments(row.expected_ipa)
        errors[row.category] += edit_distance(ref, segments(phonemes(backend, row.text, row.lang)))
        length[row.category] += len(ref)
    return {category: errors[category] / length[category] for category in length}


def noise_by_category(rows: Iterable[Row]) -> dict[str, float]:
    """One sentence's worth of PER per category.

    When every segment of an average sentence is wrong, the PER of its
    category rises by its share of the segments, which is 1 / row count.
    """
    counts = Counter(row.category for row in rows)
    return {category: 1 / n for category, n in counts.items()}


def _gain(before: dict[str, float], after: dict[str, float]) -> dict[str, float]:
    return {category: before[category] - after[category] for category in after}


def stage_gain(rows: Sequence[Row], backend: Backend, stages: Iterable[str],
               baseline: Optional[Backend] = None) -> Report:
    """Gain is error removed, so a positive number is good. PER falls as quality rises.

    ``full_vs_o2i`` is the gain of *backend* over *baseline*, which is
    standalone orthography2ipa unless given. Each stage maps to the gain of
    *backend* over the same backend without that stage, or to ``None`` when
    *backend* is not :class:`Ablatable`.
    """
    if baseline is None:
        from scriptconv.phonemizers.o2ipa import Orthography2IPAPhonemizer
        baseline = Orthography2IPAPhonemizer()
    full = per_by_category(rows, backend)
    report: Report = {"full_vs_o2i": _gain(per_by_category(rows, baseline), full)}
    for stage in stages:
        if isinstance(backend, Ablatable):
            report[stage] = _gain(per_by_category(rows, backend.without(stage)), full)
        else:
            report[stage] = None
    return report


def verdict(report: Report, stage: str, own_category: str,
            noise: float | Mapping[str, float]) -> Optional[bool]:
    """True when *stage* gains more than noise in its own category and loses
    no more than noise in any other. ``None`` when the stage is not ablatable.

    *noise* is one value for every category, or one value per category.
    """
    gains = report[stage]
    if gains is None:
        return None

    def tolerance(category: str) -> float:
        return noise[category] if isinstance(noise, Mapping) else noise

    return gains[own_category] > tolerance(own_category) and all(
        gain >= -tolerance(category)
        for category, gain in gains.items() if category != own_category)


def _load_backend(name: str) -> Backend:
    """A scriptconv phonemizer name, or ``module:attribute`` for a backend,
    a backend class or a factory that takes no arguments."""
    if ":" in name:
        module, attribute = name.split(":", 1)
        obj = getattr(importlib.import_module(module), attribute)
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
    args = parser.parse_args(argv)
    try:
        stages = _parse_stages(args.stages)
        rows, skipped = read_tsv(args.tsv, args.lang)
        backend = _load_backend(args.backend)
    except (ValueError, ImportError) as e:
        parser.error(str(e))

    reasons = ", ".join(f"{reason} {n}" for reason, n in sorted(skipped.items()))
    print(f"rows: read {len(rows) + sum(skipped.values())}, scored {len(rows)}, "
          f"skipped {sum(skipped.values())}" + (f" ({reasons})" if reasons else ""))
    if not rows:
        return 1

    failed = False
    for tier in TIERS:
        tier_rows = [row for row in rows if row.tier == tier]
        if not tier_rows:
            print(f"{tier}: no rows, no verdict")
            continue
        counts = Counter(row.category for row in tier_rows)
        noise = noise_by_category(tier_rows)
        print(f"{tier}: rows " + "  ".join(f"{c} {n}" for c, n in counts.items()))
        report = stage_gain(tier_rows, backend, [name for name, _ in stages])
        print(f"{tier}: full_vs_o2i  {_signed(report['full_vs_o2i'])}")
        for name, own in stages:
            gains = report[name]
            if gains is None:
                print(f"{tier}: {name}  not ablatable")
                continue
            if own not in gains:
                print(f"{tier}: {name}  no {own} rows, no verdict")
                continue
            passed = verdict(report, name, own, noise)
            failed = failed or (tier == "gold" and not passed)
            print(f"{tier}: {name}  {'PASS' if passed else 'FAIL'}  own {own} "
                  f"{gains[own]:+.4f} (noise {noise[own]:.4f})  {_signed(gains)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
