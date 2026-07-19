#!/usr/bin/env python
"""11_cli.py — Demonstrate the scriptconv CLI.

Usage:
    python -m scriptconv convert arpa ipa "HH AH0 L OW1"
    python -m scriptconv detect "안녕하세요"
    python -m scriptconv distribution "Hello مرحبا"
    python -m scriptconv direction "مرحبا بالعالم"
    python -m scriptconv decompose "국민"
    python -m scriptconv lang ko
"""
from scriptconv.__main__ import main

# Run the CLI with different arguments
tests = [
    ["convert", "arpa", "ipa", "HH AH0 L OW1"],
    ["convert", "ipa", "x-sampa", "ʃtʃən"],
    ["detect", "안녕하세요"],
    ["distribution", "Hello مرحبا 世界"],
    ["direction", "مرحبا بالعالم"],
    ["decompose", "국민"],
    ["lang", "ko"],
]

for argv in tests:
    print(f"$ python -m scriptconv {' '.join(argv)}")
    main(argv)
    print()
