"""French Lexique phoneme codes ↔ IPA.

Demonstrates lexique_to_ipa and ipa_to_lexique with words from Lexique383,
highlighting the N=ɲ / G=ŋ disambiguation and the two schwa codes.

Source: New, B. & Pallier, C. — Manuel de Lexique 3 v3.11, Tableau 2
(chrplr/openlexicon, CC BY-SA 4.0).
"""
from scriptconv.notation import lexique_to_ipa, ipa_to_lexique, convert, Notation

# Representative Lexique entries
entries = [
    ("b§ZuR",   "bonjour"),
    ("v5",      "vin"),
    ("bR1",     "brun"),
    ("d2",      "deux"),
    ("p9R",     "peur"),
    ("8it",     "huit"),
    ("aNo",     "agneau   (N=ɲ palatal nasal)"),
    ("kaGiG",   "camping  (G=ŋ velar nasal)"),
    ("Sa",      "chat"),
    ("Zile",    "gilet"),
    ("d@s",     "dans"),
    ("l§",      "long"),
    ("abd°Ra",  "abordera (°=schwa élidable)"),
]

print("=== Lexique → IPA ===")
for lexique, word in entries:
    ipa = lexique_to_ipa(lexique)
    print(f"  {lexique:10s} ({word:35s}) → {ipa}")

print()
print("=== IPA → Lexique ===")
ipa_samples = [
    ("bɔ̃ʒuʁ", "bonjour"),
    ("vɛ̃",    "vin"),
    ("dø",     "deux"),
    ("pœʁ",    "peur"),
    ("ɥit",    "huit"),
    ("aɲo",    "agneau"),
]
for ipa, word in ipa_samples:
    back = ipa_to_lexique(ipa)
    print(f"  {ipa:10s} ({word:10s}) → {back!r}")

print()
print("=== convert facade: Lexique → X-SAMPA (via IPA) ===")
pairs = [("Sa", "chat"), ("ZuR", "jour")]
for lexique, word in pairs:
    xs = convert(lexique, Notation.LEXIQUE, Notation.XSAMPA)
    print(f"  {lexique!r} ({word}) → X-SAMPA {xs!r}")
