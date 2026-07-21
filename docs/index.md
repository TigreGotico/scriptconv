# scriptconv documentation

scriptconv answers, in order of increasing depth: *what writing system is
this text in?* — *how do I rewrite it in another representation?* — *how do I
add, remove, or restyle its optional decorations?* — and, when explicitly
asked, *how does it sound?* Read the pages in this order for the full
zero-to-hero arc, or jump straight to the module you need.

1. **[scripts.md](scripts.md)** — writing-system identity. ISO-15924
   detection (`detect_script`, `char_script`), mixed-script segmentation
   (`script_runs`), text direction, language→script mapping with 639-1/2/3
   and variant-tag support, and the script metadata registry. The returned
   tags are stable API.
2. **[notation.md](notation.md)** — phoneme-notation transcoding through the
   IPA hub: ARPABET (with reversible stress preservation), X-SAMPA,
   Kirshenbaum, Lexique, Cotovía, RFE, Buckwalter ↔ Arabic, and the mantoq
   phonetic alphabet. The codecs-style `errors=` policy and the queryable
   `NOTATION_INFO` fidelity registry.
3. **[translit.md](translit.md)** — deterministic script-level rewriting:
   Hangul → jamo decomposition, Hiragana ↔ Katakana, and Hanzi → Cangjie
   input codes from the vendored table.
4. **[readings.md](readings.md)** — dictionary-backed respelling, where the
   answer is lexical rather than mechanical: kanji → kana (with the token
   stream and wakachigaki segmentation), hanzi → pinyin / bopomofo.
5. **[conventions.md](conventions.md)** — orthographic decorations as
   first-class data: tashkeel, kashida, Quranic marks, niqqud, teamim,
   wakachigaki, pinyin tone spelling, jamo form — with the
   `strip` / `restyle` / `apply` / `detect` algebra.
6. **[graph.md](graph.md)** — the conversion graph that ties every
   representation together: nodes, edges, lossless-preferring routing, and
   explicit extension.
7. **[phonemizers.md](phonemizers.md)** — from spelling to sound: the
   wrapper layer over G2P engines, per-language defaults with override, the
   injectable normalizer, and the licensing quarantine for vendored
   third-party engines.

Every command shown in these pages is also available from the CLI:
`python -m scriptconv --help`.
