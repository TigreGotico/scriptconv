"""Kirshenbaum (ASCII-IPA, espeak-ng's native notation) ↔ IPA."""
from scriptconv import kirshenbaum_to_ipa, ipa_to_kirshenbaum, convert

print("Kirshenbaum → IPA:")
for k in ("S", "N", "T", "D", "tS", "h@loU"):
    print(f"  {k!r:10} → {kirshenbaum_to_ipa(k)!r}")
print()

print("IPA → Kirshenbaum:")
for ipa in ("ʃ", "ŋ", "θ", "həloʊ"):
    print(f"  {ipa!r:8} → {ipa_to_kirshenbaum(ipa)!r}")
print()

# Route ARPABET → Kirshenbaum through the IPA hub.
print("ARPABET → Kirshenbaum:", convert("HH AH0 L OW1", "arpa", "kirshenbaum"))
