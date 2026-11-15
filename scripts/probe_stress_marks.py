"""Probe which backends read the stress mark (U+0301 after a vowel) as stress.

    python scripts/probe_stress_marks.py WORDS.tsv [--out CELLS.tsv] [--words-out ROWS.tsv]
                                         [--backend NAME ...] [--model BACKEND=PATH ...]
                                         [--kwarg BACKEND:NAME=VALUE ...] [--limit N]

WORDS.tsv has the columns ``lang`` and ``marked``: one word per row, with
U+0301 after the stressed vowel, as the diacritize stage writes it. The plain
word is the marked word without U+0301. For each registry backend that loads,
and each language of the file that the backend serves, the probe reads every
word plain and marked through ``phonemize_string``, with the removal of an
unread mark turned off, and gives each word one verdict:

- ``same``: the two outputs are equal;
- ``read``: the marked output stresses the marked vowel, the plain output
  stresses another vowel or none, and the consonants and the vowel count are
  equal;
- ``carried``: the marked output is the plain output with the mark in it;
- ``changed``: the outputs have the same consonants and vowel count, and
  the stress position cannot be judged (no stress in the marked output, or
  the vowel count differs from the word's vowel letters);
- ``corrupt``: anything else.

A cell is ``reads`` when no word is ``corrupt`` or ``carried``, at least one
word is ``read``, and every ``same`` word already stressed the marked vowel.
It is ``ignores`` when every word is ``same``, ``carries`` when every word is
``same`` or ``carried``, ``corrupts`` when a word is ``corrupt``, and
``partial`` otherwise. Only a ``reads`` cell may declare the language in
``stress_mark_langs``. A ``carried`` mark is the contract of a backend whose
output is its text (graphemes, codepoints); in any other backend it is a
symbol outside the phoneme set, so there it counts as ``corrupt``.
"""
import argparse
import csv
import sys
import unicodedata
from collections import Counter, defaultdict

from scriptconv.phonemizers import Phonemizer
from scriptconv.phonemizers.base import BasePhonemizer, GraphemePhonemizer, UnicodeCodepointPhonemizer
from scriptconv.phonemizers.registry import get_phonemizer

STRESS_MARK = "\u0301"

LETTER_VOWELS = set("aeiouyаеёиоуыэюяіїєәөүұӑӗӳӧӥӣӯўაეიოუաեէըիոօ")
IPA_VOWELS = set("aeiouyæøœɐɑɒɔəɘɛɜɞɤɨɪɯɵɶʉʊʌʏɚɝᵻɿʮɷ")
STRESS_SYMBOLS = set("ˈˌ")
NON_SYLLABIC, SYLLABIC = "\u032f", "\u0329"
# Backends whose output is the text itself.
TEXT_BACKENDS = (GraphemePhonemizer, UnicodeCodepointPhonemizer)


def letter_vowels(word: str):
    """Indices, among the letters of *word*, of its vowel letters, and the vowel the mark follows."""
    vowels, marked, seen = [], None, -1
    for c in unicodedata.normalize("NFD", word):
        if c == STRESS_MARK:
            marked = len(vowels) - 1 if vowels and vowels[-1] == seen else None
            continue
        if unicodedata.combining(c):
            continue
        seen += 1
        if c.lower() in LETTER_VOWELS:
            vowels.append(seen)
    return vowels, marked


def ipa_segments(phonemes: str):
    """Nuclei count, stressed nucleus index, and consonant skeleton of IPA *phonemes*."""
    chars = unicodedata.normalize("NFD", phonemes.strip())
    nuclei, stressed, pending, skeleton = 0, None, False, []
    for i, c in enumerate(chars):
        if c in STRESS_SYMBOLS:
            pending = pending or c == "ˈ"
            continue
        marks = []
        j = i + 1
        while j < len(chars) and unicodedata.combining(chars[j]):
            marks.append(chars[j])
            j += 1
        if unicodedata.combining(c) or c in "ːˑ" or c.isspace():
            continue
        if (c.lower() in IPA_VOWELS and NON_SYLLABIC not in marks) or SYLLABIC in marks:
            if pending and stressed is None:
                stressed = nuclei
            pending = False
            nuclei += 1
        else:
            skeleton.append(c)
    return nuclei, stressed, "".join(skeleton)


def vosk_segments(phonemes: str):
    """The same for Vosk tokens, whose vowels carry a stress digit (``a1`` stressed)."""
    tokens = phonemes.split()
    vowels = [t for t in tokens if t[-1:] in "01" and t[:-1] and t[:-1][0] in "aeiouy"]
    stressed = next((k for k, t in enumerate(vowels) if t.endswith("1")), None)
    return len(vowels), stressed, " ".join(t for t in tokens if t not in vowels)


def verdict(word, plain_out, marked_out, segments, text_backend):
    """The verdict of one word, and whether the plain output stressed the marked vowel (None: not judged)."""
    vowels, marked = letter_vowels(word)
    n_plain, s_plain, k_plain = segments(plain_out)
    n_marked, s_marked, k_marked = segments(marked_out)
    judged = marked is not None and len(vowels) >= 2 and n_plain == n_marked == len(vowels)
    # None when the plain stress position cannot be judged
    plain_on_mark = s_plain == marked if judged and s_plain is not None else None
    if plain_out == marked_out:
        return "same", plain_on_mark
    if STRESS_MARK in marked_out and marked_out.replace(STRESS_MARK, "") == plain_out:
        return ("carried" if text_backend else "corrupt"), plain_on_mark
    if k_plain != k_marked or n_plain != n_marked:
        return "corrupt", plain_on_mark
    if not judged or s_marked is None:
        return "changed", plain_on_mark
    if s_marked == marked and s_plain != marked:
        return "read", plain_on_mark
    return "corrupt", plain_on_mark


def classify(counts: Counter, same_off_mark: int) -> str:
    if counts["corrupt"]:
        return "corrupts"
    if counts["same"] == sum(counts.values()):
        return "ignores"
    if counts["carried"]:
        return "carries" if counts["carried"] + counts["same"] == sum(counts.values()) else "partial"
    if counts["read"] and not same_off_mark:
        return "reads"
    return "partial"


def serves(phonemizer: BasePhonemizer, lang: str) -> bool:
    if not hasattr(phonemizer, "get_lang"):
        return True
    try:
        phonemizer.get_lang(lang)
    except Exception:
        return False
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("words")
    parser.add_argument("--out")
    parser.add_argument("--words-out")
    parser.add_argument("--backend", action="append", default=[])
    parser.add_argument("--model", action="append", default=[], metavar="BACKEND=PATH")
    parser.add_argument("--kwarg", action="append", default=[], metavar="BACKEND:NAME=VALUE")
    parser.add_argument("--limit", type=int, help="read at most N words per language")
    args = parser.parse_args(argv)

    words = defaultdict(list)
    with open(args.words, encoding="utf-8") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))
    for row in rows:
        if STRESS_MARK in row["marked"] and row["marked"] not in words[row["lang"]]:
            words[row["lang"]].append(row["marked"])
    print(f"words: {len(rows)} rows in, {sum(map(len, words.values()))} unique marked words "
          f"in {len(words)} languages", file=sys.stderr)

    models = dict(m.split("=", 1) for m in args.model)
    kwargs = defaultdict(dict)
    for option in args.kwarg:
        backend, _, assignment = option.partition(":")
        name, _, value = assignment.partition("=")
        kwargs[backend][name] = value
    cells, word_rows = [], []
    for member in Phonemizer:
        if args.backend and member.value not in args.backend:
            continue
        try:
            phonemizer = get_phonemizer(member, model=models.get(member.value), **kwargs[member.value])
        except Exception as e:
            print(f"{member.value}: not loaded ({type(e).__name__}: {str(e)[:120]})", file=sys.stderr)
            continue
        # read the engine itself: no mark is removed before it
        phonemizer.reads_stress_mark = lambda lang: True
        segments = vosk_segments if member is Phonemizer.VOSK else ipa_segments
        text_backend = isinstance(phonemizer, TEXT_BACKENDS)
        for lang, marked_words in words.items():
            if not serves(phonemizer, lang):
                continue
            counts, same_off_mark, errors = Counter(), 0, 0
            marked_words = marked_words[:args.limit]
            for word in marked_words:
                plain = word.replace(STRESS_MARK, "")
                try:
                    plain_out = phonemizer.phonemize_string(plain, lang)
                    marked_out = phonemizer.phonemize_string(word, lang)
                except Exception:
                    errors += 1
                    continue
                result, plain_on_mark = verdict(word, plain_out, marked_out, segments, text_backend)
                counts[result] += 1
                same_off_mark += result == "same" and plain_on_mark is False
                word_rows.append({"backend": member.value, "lang": lang, "marked": word,
                                  "plain_out": plain_out, "marked_out": marked_out,
                                  "verdict": result})
            n_out = sum(counts.values())
            cell = classify(counts, same_off_mark) if n_out else "no output"
            cells.append({"backend": member.value, "lang": lang, "n_in": len(marked_words),
                          "n_out": n_out, "errors": errors, "cell": cell,
                          **{k: counts[k] for k in ("read", "same", "carried", "changed", "corrupt")},
                          "same_off_mark": same_off_mark})
            print(f"{member.value}\t{lang}\t{len(marked_words)} in\t{n_out} out\t{cell}\t{dict(counts)}",
                  file=sys.stderr)
        close = getattr(phonemizer, "close", None)
        if close:
            close()

    fields = ["backend", "lang", "n_in", "n_out", "errors", "cell",
              "read", "same", "carried", "changed", "corrupt", "same_off_mark"]
    out = open(args.out, "w", encoding="utf-8", newline="") if args.out else sys.stdout
    writer = csv.DictWriter(out, fieldnames=fields, delimiter="\t")
    writer.writeheader()
    writer.writerows(cells)
    if args.words_out:
        with open(args.words_out, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(word_rows[0]) if word_rows else ["backend"],
                                    delimiter="\t")
            writer.writeheader()
            writer.writerows(word_rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
