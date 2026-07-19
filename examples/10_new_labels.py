"""New normalize_script_tag labels — Japanese, Jamo, CJK, etc."""
from scriptconv import normalize_script_tag

labels = [
    "japanese", "jamo", "hangul jamo", "devanagari extended",
    "ipa", "cjk", "chinese characters", "hangeul",
    "bangla", "punjabi", "kannada", "odia",
]

for label in labels:
    code = normalize_script_tag(label)
    print(f"  {label!r:30s} → {code}")
