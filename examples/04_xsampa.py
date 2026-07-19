"""X-SAMPA ↔ IPA conversion, with multi-character longest-first matching.

Highlights cases where greedy longest-first matching is required to avoid
mis-splitting multi-character X-SAMPA symbols.
"""
from scriptconv.notation import xsampa_to_ipa, ipa_to_xsampa

# Single-symbol basics
basics = [
    ("S",  "palato-alveolar fricative"),
    ("Z",  "voiced palato-alveolar fricative"),
    ("@",  "schwa"),
    ("E",  "open-mid front unrounded"),
    ("I",  "near-close near-front unrounded"),
    ("A",  "open back unrounded"),
    ("O",  "open-mid back rounded"),
    ("N",  "velar nasal"),
    ('"',  "primary stress mark"),
    (":",  "length mark"),
]

print("=== X-SAMPA → IPA (single symbols) ===")
for xs, note in basics:
    print(f"  {xs!r:5s}  ({note:40s}) → {xsampa_to_ipa(xs)!r}")

# Multi-char cases that require longest-first matching
multi = [
    ("tS",   "palato-alveolar affricate (NOT t + ʃ)"),
    ("dZ",   "voiced affricate (NOT d + ʒ)"),
    ("r\\",  "approximant r (before plain r)"),
    ("ts`",  "retroflex affricate (longest first)"),
    ("@\\",  "close-mid central (before @=ə)"),
    ("@`",   "r-coloured schwa (before @=ə)"),
    ("N\\",  "uvular nasal (before N=ŋ)"),
    ("G\\",  "voiced uvular stop (before G=ɣ)"),
    ("{",    "near-open front unrounded (æ)"),
    ("}",    "close central rounded (ʉ)"),
]

print()
print("=== X-SAMPA → IPA (multi-char, longest-first required) ===")
for xs, note in multi:
    print(f"  {xs!r:6s}  ({note:45s}) → {xsampa_to_ipa(xs)!r}")

# IPA → X-SAMPA
print()
print("=== IPA → X-SAMPA ===")
ipa_samples = [
    "tʃ", "dʒ", "ɹ", "æ", "ʉ", "ŋ", "ʃ", "ʒ", "ə", "ɔ",
]
for ipa in ipa_samples:
    print(f"  {ipa!r:6s} → {ipa_to_xsampa(ipa)!r}")

# Full word
print()
word_xs = '"tS@n'
print(f"=== Word example: {word_xs!r} ===")
print(f"  → {xsampa_to_ipa(word_xs)!r}")
