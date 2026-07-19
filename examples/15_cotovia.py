"""Cotovía (Universidade de Vigo Galician TTS notation) ↔ IPA."""
from scriptconv import cotovia_to_ipa, ipa_to_cotovia, convert

print("Cotovía → IPA:")
for cv in ("tS", "karro", "kara", "L", "GaTo"):
    print(f"  {cv!r:8} → {cotovia_to_ipa(cv)!r}")
print()

print("IPA → Cotovía:")
for ipa in ("tʃ", "ʎ", "ɲo"):
    print(f"  {ipa!r:6} → {ipa_to_cotovia(ipa)!r}")
print()

# Route Cotovía → X-SAMPA through the IPA hub.
print("Cotovía → X-SAMPA:", convert("tS", "cotovia", "x-sampa"))
