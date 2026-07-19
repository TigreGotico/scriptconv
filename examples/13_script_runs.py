"""Segment mixed-script text into per-script runs (structure, not one label)."""
from scriptconv import script_runs, detect_script

for text in ("привет hello", "Hello مرحبا world", "日本語 and English"):
    print(f"{text!r}")
    print(f"  dominant : {detect_script(text)}")
    print(f"  runs     : {script_runs(text)}")
    print()
