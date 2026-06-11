"""Language tag to ISO-15924 script mapping.

Demonstrates lang_to_script with BCP-47 tags, bare ISO 639 codes,
and the normalize_script_tag utility for free-form labels.
"""
from scriptconv.scripts import lang_to_script, normalize_script_tag

lang_samples = [
    ("en",    "English"),
    ("pt-BR", "Portuguese (Brazil)"),
    ("ru-RU", "Russian (Russia)"),
    ("ar",    "Arabic"),
    ("zh",    "Chinese"),
    ("ja",    "Japanese"),
    ("ko",    "Korean"),
    ("hi",    "Hindi"),
    ("ka",    "Georgian"),
    ("hy",    "Armenian"),
    ("crk",   "Plains Cree"),
    ("bo",    "Tibetan"),
    ("my",    "Burmese"),
    ("lo",    "Lao"),
    ("xyz",   "Unknown"),
]

print("=== lang_to_script ===")
for lang, name in lang_samples:
    result = lang_to_script(lang)
    print(f"  {lang:8s}  {name:25s} → {result!r}")

label_samples = [
    "latin", "Cyrillic", "ARABIC", "syllabics",
    "Korean", "Chinese", "burmese", "lao",
    "Latn", "latn", "arab",
    "unknown_xyz",
]

print()
print("=== normalize_script_tag ===")
for label in label_samples:
    result = normalize_script_tag(label)
    print(f"  {label!r:35s} → {result!r}")
