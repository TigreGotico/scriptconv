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

usage: python scripts/time_owner_backends.py PROSE_DIR

PROSE_DIR holds ``en.txt``, ``pt.txt``, ``eu.txt`` and ``ar.txt``.
"""
import statistics
import sys
import time
from pathlib import Path

from scriptconv.phonemizers import Phonemizer
from scriptconv.phonemizers.registry import get_phonemizer_class

RUNS = 5
CHARS = 10_000
TARGET_MS = 100

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


if __name__ == "__main__":
    main(Path(sys.argv[1]))
