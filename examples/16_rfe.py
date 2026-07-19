"""RFE (Revista de Filología Española) Spanish/Romance phonetic notation ↔ IPA."""
from scriptconv import rfe_to_ipa, ipa_to_rfe, convert

print("RFE → IPA:")
for r in ("š", "kaša", "ñ", "far̄a", "ĉiko"):
    print(f"  {r!r:8} → {rfe_to_ipa(r)!r}")
print()

print("IPA → RFE:")
for ipa in ("ʃ", "ɲ", "ʎ", "tʃ"):
    print(f"  {ipa!r:6} → {ipa_to_rfe(ipa)!r}")
print()

print("RFE → X-SAMPA:", convert("š", "rfe", "x-sampa"))
