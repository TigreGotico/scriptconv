"""ARPABET ↔ IPA conversion — CMUdict-style lines.

Demonstrates arpa_to_ipa, ipa_to_arpa, the AH0→ə special case,
stress-digit stripping, and the unknown-symbol policy.

Table derived from chorusai/arpa2ipa (Apache-2.0).
"""
from scriptconv.notation import arpa_to_ipa, ipa_to_arpa

# CMUdict-style entries: WORD  ARPA sequence
cmudict_lines = [
    ("HELLO",    "HH AH0 L OW1"),
    ("JUST",     "JH AH1 S T"),
    ("THANKS",   "TH AE1 NG K S"),
    ("SHOW",     "SH OW1"),
    ("THINK",    "TH IH1 NG K"),
    ("BUTTER",   "B AH1 T ER0"),
    ("RHYTHM",   "R IH1 DH AH0 M"),
    ("SING",     "S IH1 NG"),
]

print("=== ARPABET → IPA ===")
for word, arpa in cmudict_lines:
    ipa = arpa_to_ipa(arpa)
    print(f"  {word:10s}  {arpa:30s} → {ipa}")

print()
print("=== IPA → ARPABET ===")
ipa_samples = [
    ("həloʊ",  "hello"),
    ("θæŋks",  "thanks"),
    ("dʒʌst",  "just"),
    ("ŋ",      "eng"),
    ("ɸ",      "phi (not in ARPABET)"),
]
for ipa, note in ipa_samples:
    back = ipa_to_arpa(ipa)
    print(f"  {ipa:10s}  ({note:25s}) → {back!r}")

print()
print("=== Stress digit edge cases ===")
for token, note in [
    ("AH0", "unstressed → schwa"),
    ("AH1", "primary stress → ʌ"),
    ("AH2", "secondary stress → ʌ"),
    ("AX",  "CMU AX variant → schwa"),
    ("AXR", "r-coloured schwa"),
    ("EL",  "syllabic l"),
    ("EM",  "syllabic m"),
    ("EN",  "syllabic n"),
]:
    print(f"  {token:6s}  ({note:30s}) → {arpa_to_ipa(token)!r}")

print()
print("=== Unknown-symbol policy ===")
print(f"  ipa_to_arpa('ɸ')          → {ipa_to_arpa('ɸ')!r}   (default unknown='?')")
print(f"  ipa_to_arpa('ɸ', unknown='') → {ipa_to_arpa('ɸ', unknown='')!r} (drop silently)")
