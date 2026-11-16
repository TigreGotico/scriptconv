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
are loaded before the clock starts. The garbage collector runs once before
the clock starts and stays on during the read, as in a process that serves
the frontend, so a collection that the read itself sets off is in the time.
A full collection of a process that holds many other objects can still add
to one call. A ``reads_whole_text`` backend runs
``phonemize_segments``. Any other backend runs ``phonemize_to_list``, its
whole-text path.

A text dense in dates, prices and abbreviations costs more per character
than prose, and the cost does not grow in a straight line. A blank line or a
quotation mark costs more again, because the backend maps each one to its
place in the output. So each ``reads_whole_text`` backend also reads three
shapes of a dense English text at each of :data:`SIZES` characters: the
sentences in one run (``dense``), with a blank line after each
(``dense+blank``), and each in quotes as well (``dense+quote+blank``). The
script reports the median and the maximum of the runs, and the largest size
at which the maximum of every shape stays under 100 ms, and so does every
smaller size. A server reads the same backend many times in one process, with
no collection before the clock, and that steady mode can be slower than a
fresh backend. ``WHOLE_TEXT_LIMIT`` is the largest size at which every run of
this script and every run of the steady mode stays under 100 ms, each started
at a 1-minute load of 8 or less on a 24-core machine.
``scripts/time_owner_backends.txt`` holds the output.

usage: python scripts/time_owner_backends.py PROSE_DIR

PROSE_DIR holds ``en.txt``, ``pt.txt``, ``eu.txt`` and ``ar.txt``.
"""
import gc
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
SIZES = range(1000, 4001, 250)

_DENSE_PARTS = ("On Jan. 5, 2024 Dr. Smith paid $1,250.50 for 3.5 kg at 4:30 p.m.",
                "See p. 12 and No. 5; the est. time is 2.5 hrs.",
                "Call 555-0134 or visit 221B Baker St. by 12/03/2024.",
                "The U.S. GDP grew 3.2% in Q3, i.e. $27.4 trillion.",
                "Mr. and Mrs. Jones met Prof. Lee at 10:15 a.m.",
                "Room 4B, Bldg. 7, Apt. 12 costs 1,200 EUR/mo.")
_RANDOM = random.Random(1)
_PICKS = [_RANDOM.choice(_DENSE_PARTS) for _ in range(400)]
SHAPES = {"dense": " ".join(_PICKS),
          "dense+blank": "\n\n".join(_PICKS),
          "dense+quote+blank": "\n\n".join(f'"{part}"' for part in _PICKS)}
"""English text dense in dates, prices and abbreviations, in three shapes."""

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
        gc.collect()
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
        print(f"| {member.value} | Characters | " + " | ".join(f"{shape} median, max ms" for shape in SHAPES) + " |")
        print("| --- | --- |" + " --- |" * len(SHAPES))
        fits, smaller_fit = None, True
        for size in SIZES:
            times = {shape: time_backend(cls, lang, text[:size], warm_up) for shape, text in SHAPES.items()}
            print(f"| | {size} | " + " | ".join(f"{statistics.median(runs):.1f}, {max(runs):.1f}"
                                               for runs in times.values()) + " |")
            smaller_fit = smaller_fit and max(map(max, times.values())) < TARGET_MS
            if smaller_fit:
                fits = size
        print(f"{member.value}: largest size with every run of every shape under {TARGET_MS} ms: {fits}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
