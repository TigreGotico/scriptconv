"""Reverse language lookup — which languages use a given script?"""
from scriptconv import script_to_langs, lang_to_script

# Which languages use Cyrillic?
cyrl_langs = script_to_langs("Cyrl")
print(f"Languages using Cyrillic ({len(cyrl_langs)}): {cyrl_langs[:10]}...")
print()

# Which languages use Latin?
latn_langs = script_to_langs("Latn")
print(f"Languages using Latin ({len(latn_langs)}): {latn_langs[:10]}...")
print()

# Round-trip: lang → script → langs
for lang in ("ru", "ar", "hi", "ko", "zh"):
    script = lang_to_script(lang)
    langs_back = script_to_langs(script)
    print(f"  {lang} → {script} → {langs_back[:5]}...")
