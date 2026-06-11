"""Mixed-script text triage using detect_script and char_script.

Shows how to identify the dominant writing system in a string and how to
inspect individual characters in mixed-script input.
"""
from scriptconv.scripts import detect_script, char_script

samples = [
    ("English",    "Hello world"),
    ("Russian",    "Привет мир"),
    ("Arabic",     "مرحبا بالعالم"),
    ("Korean",     "안녕하세요"),
    ("Greek",      "ελληνικά"),
    ("Chinese",    "中文测试"),
    ("Mixed (Cyrillic dominant)", "Привет A world"),
    ("Mixed (Arabic dominant)",   "مرحبا hello مرحبا"),
    ("Lao",        "ສະບາຍດີ"),
    ("Tibetan",    "བོད་སྐད།"),
    ("Numbers only", "123 456"),
    ("Empty",      ""),
]

print("=== detect_script ===")
for label, text in samples:
    result = detect_script(text)
    print(f"  {label:35s} → {result!r}")

print()
print("=== char_script — mixed word ===")
word = "Héllo"
for ch in word:
    print(f"  {ch!r:5s} → {char_script(ch)!r}")
