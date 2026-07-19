"""CLI interface for scriptconv.

Usage
-----
    python -m scriptconv convert <src> <dst> <text>
    python -m scriptconv detect <text>
    python -m scriptconv distribution <text>
    python -m scriptconv direction <text>
    python -m scriptconv decompose <text>
    python -m scriptconv lang <code>

Examples
--------
    python -m scriptconv convert arpa ipa "HH AH0 L OW1"
    python -m scriptconv detect "안녕하세요"
    python -m scriptconv decompose "국민"
"""
from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="scriptconv",
        description="Script and phoneme notation conversion tools.",
    )
    sub = p.add_subparsers(dest="command")

    conv = sub.add_parser("convert", help="Convert text between notations")
    conv.add_argument("src", help="Source notation")
    conv.add_argument("dst", help="Destination notation")
    conv.add_argument("text", help="Text to convert")

    det = sub.add_parser("detect", help="Detect dominant script")
    det.add_argument("text", help="Text to analyse")

    dist = sub.add_parser("distribution", help="Show script character counts")
    dist.add_argument("text", help="Text to analyse")

    dirc = sub.add_parser("direction", help="Detect base text direction")
    dirc.add_argument("text", help="Text to analyse")

    decomp = sub.add_parser("decompose", help="Decompose Hangul into jamo")
    decomp.add_argument("text", help="Text to decompose")

    lang = sub.add_parser("lang", help="Map language code to script")
    lang.add_argument("code", help="BCP-47 or ISO 639 language code")

    args = p.parse_args(argv)

    if args.command is None:
        p.print_help()
        return 1

    dispatch = {
        "convert": lambda: _do_convert(args),
        "detect": lambda: _do_detect(args),
        "distribution": lambda: _do_distribution(args),
        "direction": lambda: _do_direction(args),
        "decompose": lambda: _do_decompose(args),
        "lang": lambda: _do_lang(args),
    }
    dispatch[args.command]()
    return 0


def _do_convert(args: argparse.Namespace) -> None:
    from scriptconv.notation import Notation, convert
    try:
        print(convert(args.text, args.src, args.dst))
    except ValueError as e:
        valid = ", ".join(n.value for n in Notation)
        raise SystemExit(f"error: {e} (valid notations: {valid})")


def _do_detect(args: argparse.Namespace) -> None:
    from scriptconv.scripts import detect_script
    print(detect_script(args.text) or "(none)")


def _do_distribution(args: argparse.Namespace) -> None:
    from scriptconv.scripts import script_distribution
    dist = script_distribution(args.text)
    if not dist:
        print("(no script-bearing characters)")
    else:
        for code, count in dist.items():
            print(f"  {code}: {count}")


def _do_direction(args: argparse.Namespace) -> None:
    from scriptconv.scripts import base_direction
    print(base_direction(args.text))


def _do_decompose(args: argparse.Namespace) -> None:
    from scriptconv.translit import decompose_hangul
    print(decompose_hangul(args.text))


def _do_lang(args: argparse.Namespace) -> None:
    from scriptconv.scripts import lang_to_script
    print(lang_to_script(args.code) or "(unknown)")


if __name__ == "__main__":
    sys.exit(main())
