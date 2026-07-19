"""Arabic script ↔ Buckwalter transliteration, both directions.

Covers letters, short-vowel diacritics, hamza variants, and the shadda
gemination marker. Follows Tim Buckwalter's transliteration scheme.
"""
from scriptconv.notation import buckwalter_to_arabic, arabic_to_buckwalter

# Words
words = [
    ("mrHbA",      "مرحبا",  "marhaba / hello"),
    ("AlkitAb",    "الكتاب", "al-kitab / the book"),
    ("Eyn",        "عين",    "ayn / eye"),
    ("$ms",        "شمس",    "shams / sun"),
    ("qmr",        "قمر",    "qamar / moon"),
    ("AlqrAn",     "القرآن", "al-quran (note: آ = |)"),
]

print("=== Buckwalter → Arabic ===")
for bw, arabic, note in words:
    result = buckwalter_to_arabic(bw)
    print(f"  {bw:12s} → {result}  ({note})")

print()
print("=== Arabic → Buckwalter ===")
for bw, arabic, note in words:
    result = arabic_to_buckwalter(arabic)
    print(f"  {arabic}  ({note}) → {result!r}")

# Diacritics and special characters
print()
print("=== Diacritics and special characters ===")
special = [
    ("a",  "فَ",  "fatha (short a)"),
    ("u",  "فُ",  "damma (short u)"),
    ("i",  "فِ",  "kasra (short i)"),
    ("~",  "فّ",  "shadda (gemination)"),
    ("o",  "فْ",  "sukun (no vowel)"),
    ("F",  "فً",  "tanwin fath"),
    ("N",  "فٌ",  "tanwin damm"),
    ("K",  "فٍ",  "tanwin kasr"),
    (">",  "أ",   "alef + hamza above"),
    ("<",  "إ",   "alef + hamza below"),
    ("|",  "آ",   "alef madda"),
    ("&",  "ؤ",   "waw + hamza"),
    ("}",  "ئ",   "ya + hamza"),
]
for bw, arabic, note in special:
    result_fwd = buckwalter_to_arabic(bw)
    result_bwd = arabic_to_buckwalter(arabic)
    print(f"  BW {bw!r:3s} → Arabic {result_fwd!r:3s}  |  Arabic {arabic!r:3s} → BW {result_bwd!r}   ({note})")
