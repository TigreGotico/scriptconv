"""Time one whole-text read of each backend that reads text with its own rules.

``WHOLE_TEXT_LIMIT`` in ``scriptconv/frontend.py`` comes from this timing. One
call of the slowest backend that reads whole text must stay under 100 ms. The
script times every registry backend that names ``normalize`` in
``owned_stages``, and the backends whose library reads raw text with its own
rules, for the record. A backend whose extra is missing is reported and
skipped.

Each backend reads 10,000 characters of plain prose in its language: one call,
in one process, the median of 5 runs. Each run builds a new backend and
warms it with one short sentence, so word caches start empty and lazy models
are loaded before the clock starts. A ``reads_whole_text`` backend runs
``phonemize_segments``. Any other backend runs ``phonemize_to_list``, its
whole-text path.

A text dense in dates, prices and abbreviations costs more per character
than prose, and the cost does not grow in a straight line. So each
``reads_whole_text`` backend also reads the prose and a dense English text at
each of :data:`SIZES` characters. The time of dense text varies by a
quarter from run to run, so the script reports the largest size at which
the median of both texts stays under 75 ms, a quarter under the target, and
so does every smaller size. Run the script several times on an idle machine:
``WHOLE_TEXT_LIMIT`` is the smallest size that a run reports.

usage: python scripts/time_owner_backends.py PROSE_DIR

PROSE_DIR holds ``en.txt``, ``pt.txt``, ``eu.txt`` and ``ar.txt``.
"""
import random
import statistics
import sys
import time
from pathlib import Path

from scriptconv.phonemizers import Phonemizer
from scriptconv.phonemizers.registry import get_phonemizer_class

RUNS = 5
CHARS = 10_000
TARGET_MS = 100
HEADROOM = 0.75
SIZES = (6000, 5000, 4000, 3500, 3000, 2500)

_DENSE_PARTS = ("On Jan. 5, 2024 Dr. Smith paid $1,250.50 for 3.5 kg at 4:30 p.m.",
                "See p. 12 and No. 5; the est. time is 2.5 hrs.",
                "Call 555-0134 or visit 221B Baker St. by 12/03/2024.",
                "The U.S. GDP grew 3.2% in Q3, i.e. $27.4 trillion.",
                "Mr. and Mrs. Jones met Prof. Lee at 10:15 a.m.",
                "Room 4B, Bldg. 7, Apt. 12 costs 1,200 EUR/mo.")
_RANDOM = random.Random(1)
DENSE = " ".join(_RANDOM.choice(_DENSE_PARTS) for _ in range(400))
"""English text dense in dates, prices and abbreviations."""

# backend -> (language tag, prose file, warm-up sentence)
BACKENDS = {
    Phonemizer.DIZIONE: ("en-US", "en", "The cat sat."),
    Phonemizer.TUGAPHONE: ("pt-PT", "pt", "O gato dorme."),
    Phonemizer.EUSKAPHONE: ("eu", "eu", "Katua lo dago."),
    Phonemizer.ARBTOK: ("ar", "ar", "القط نائم."),
    Phonemizer.SHAMI: ("ar", "ar", "القط نائم."),
}


def time_backend(cls, lang, text, warm_up):
    """The time of each run, in milliseconds."""
    times = []
    for _ in range(RUNS):
        backend = cls()
        if cls.reads_whole_text:
            def read(text):
                return list(backend.phonemize_segments(text, lang))
        else:
            def read(text):
                return backend.phonemize_to_list(text, lang)
        read(warm_up)
        start = time.perf_counter()
        read(text)
        times.append((time.perf_counter() - start) * 1000)
    return times


def main(prose_dir):
    rows = []
    for member, (lang, prose, warm_up) in BACKENDS.items():
        try:
            cls = get_phonemizer_class(member)
        except ImportError as e:
            print(f"{member.value}: skipped, {e}")
            continue
        text = (prose_dir / f"{prose}.txt").read_text(encoding="utf-8")[:CHARS]
        times = time_backend(cls, lang, text, warm_up)
        median = statistics.median(times)
        rows.append((member.value, cls, len(text), median, times))
    print("| Backend | Owns normalize | Reads whole text | Characters | Median ms | Runs ms |")
    print("| --- | --- | --- | --- | --- | --- |")
    for name, cls, chars, median, times in rows:
        print(f"| {name} | {'normalize' in cls.owned_stages} | {cls.reads_whole_text} | {chars} "
              f"| {median:.1f} | {', '.join(f'{t:.1f}' for t in times)} |")
    whole = [(median / chars, name) for name, cls, chars, median, _ in rows if cls.reads_whole_text]
    if whole:
        per_char, name = max(whole)
        limit = int(TARGET_MS / per_char)
        print(f"slowest whole-text backend: {name}, {per_char * 1000:.2f} ms per 1,000 characters; "
              f"{TARGET_MS} ms reads {limit} characters")
    for member, (lang, prose, warm_up) in BACKENDS.items():
        cls = next((cls for name, cls, *_ in rows if name == member.value), None)
        if cls is None or not cls.reads_whole_text:
            continue
        texts = {"prose": (prose_dir / f"{prose}.txt").read_text(encoding="utf-8"), "dense": DENSE}
        fits, smaller_fit = None, True
        for size in sorted(SIZES):
            medians = {name: statistics.median(time_backend(cls, lang, text[:size], warm_up))
                       for name, text in texts.items()}
            print(f"{member.value} {size} characters: "
                  + ", ".join(f"{name} {median:.1f} ms" for name, median in medians.items()))
            smaller_fit = smaller_fit and max(medians.values()) < HEADROOM * TARGET_MS
            if smaller_fit:
                fits = size
        print(f"{member.value}: largest size under {HEADROOM * TARGET_MS:.0f} ms for prose and dense "
              f"text: {fits}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
