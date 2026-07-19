"""Hiragana ↔ Katakana — same syllabary, fixed codepoint offset."""
from scriptconv import hira_to_kana, kana_to_hira

print("Hiragana → Katakana:", hira_to_kana("こんにちは"))
print("Katakana → Hiragana:", kana_to_hira("カタカナ"))
# Round-trip
s = "ありがとう"
print("round-trip:", kana_to_hira(hira_to_kana(s)) == s)
