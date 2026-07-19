"""Hangul syllable block decomposition into jamo letters.

Demonstrates the purely orthographic nature of decompose_hangul:
jamo are extracted by arithmetic on the Unicode codepoint, with no
phonological rules applied (no nasal assimilation, no coda neutralisation).

Jamo tables derived from stannam/hangul_to_ipa.
"""
from scriptconv.translit import decompose_hangul

words = [
    ("한",     "han"),
    ("한국어",  "hangugeo (Korean language)"),
    ("가",     "ga — no coda; empty slot omitted"),
    ("값",     "gabs — compound coda ㅄ preserved as written"),
    ("국민",   "gungmin — written ㄱ+ㅁ, pronounced [ŋm] (no assimilation applied)"),
    ("안녕",   "annyeong / hello"),
    ("서울",   "Seoul"),
    ("대한민국", "Republic of Korea"),
]

print("=== decompose_hangul ===")
for text, note in words:
    result = decompose_hangul(text)
    print(f"  {text:8s}  ({note})")
    print(f"           → {result!r}")
    print()

print("=== Mixed text (non-Hangul passes through) ===")
mixed = [
    "hello 한 world",
    "123 abc",
    "",
    "서울 Seoul",
]
for text in mixed:
    print(f"  {text!r:25s} → {decompose_hangul(text)!r}")

print()
print("=== Scope note ===")
print("  decompose_hangul applies no phonological rules.")
print("  국민 written: ㄱㅜㄱㅁㅣㄴ   (orthographic jamo)")
print("  국민 spoken:  [ɡuŋmin]       (nasal assimilation ㄱ→ㅇ)")
print("  decompose_hangul returns the written form only.")
