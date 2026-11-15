"""Try the phonemizer on a sentence.

    python -m dizione "Hello, it costs $3.50."
    python -m dizione --words "I read the book I read yesterday."

Prints the token sequence (stress marks on the phones, <sp> between words).
``--words`` also shows where each word's pronunciation came from.
"""

import argparse
from pathlib import Path

from .convert import to_text
from .engine import Phonemizer
from .sentence import groups
from .symbols import tokenize


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("text", nargs="+")
    parser.add_argument("--data", type=Path, help="Built data directory (default: DIZIONE_DATA)")
    parser.add_argument("--overrides", type=Path, help="Table of your own pronunciations: word, two spaces, pronunciation")
    parser.add_argument("--no-phrases", action="store_true", help="Keep a word boundary inside groups such as 'of the'")
    parser.add_argument("--words", action="store_true", help="Show every word and the source of its pronunciation")
    args = parser.parse_args()
    phonemizer = Phonemizer(args.data, overrides=args.overrides, join_phrases=not args.no_phrases)
    for sentence_text in args.text:
        analysis = phonemizer.analyse(sentence_text)
        print(tokenize([(True, value) if kind == "punct" else (False, groups(value)) for kind, value in analysis]))
        if args.words:
            for kind, value in analysis:
                if kind == "punct":
                    print(f"  {value}")
                    continue
                for unit in value:
                    print(f"  {unit.word:24s} {unit.source:10s} {to_text(unit.phones)}")


if __name__ == "__main__":
    main()
