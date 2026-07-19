"""Script distribution — count characters per writing system."""
from scriptconv import script_distribution, base_direction

# Mixed-script text
text = "Hello مرحبا Привет こんにちは"
dist = script_distribution(text)
print(f"Text: {text!r}")
print(f"Script distribution: {dist}")
print(f"Base direction: {base_direction(text)}")
print()

# Pure RTL
arabic = "بسم الله الرحمن الرحيم"
print(f"Arabic: {arabic!r}")
print(f"  direction: {base_direction(arabic)}")
print(f"  distribution: {script_distribution(arabic)}")
print()

# Pure LTR
latin = "The quick brown fox"
print(f"English: {latin!r}")
print(f"  direction: {base_direction(latin)}")
print(f"  distribution: {script_distribution(latin)}")
