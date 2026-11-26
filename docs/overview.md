# scriptconv overview

<!-- agent-hint
covers: the four ideas of scriptconv, a tour of each module with examples, and the related projects
source: `__all__` in scriptconv/__init__.py, scriptconv/scripts.py, scriptconv/notation.py, scriptconv/graph.py, scriptconv/phonemizers/__init__.py
generated: no
verify: python scripts/check_doc_page.py docs/overview.md
see: index.md, stack.md, reference.md
-->

## The model

scriptconv is organized around four ideas, layered from identity to sound.

1. **Scripts are identity.** A character belongs to a writing system
   (ISO 15924: `Latn`, `Cyrl`, `Arab`, and so on), detectable from the text
   itself, and identity never changes what the text *means*.

2. **Representations are nodes. Conversions are edges.** IPA, ARPABET,
   hiragana, pinyin, and Cangjie codes are each a node in one conversion
   graph, and asking for `halabi → x-sampa` finds the cheapest path
   (`halabi → ipa → x-sampa`), preferring lossless edges by construction.

3. **Conventions are decorations, not identities.** Arabic vowel marks,
   Hebrew points, Japanese word spacing, and pinyin tone spelling are
   parameters a script's text can carry or omit (`strip`, `restyle`,
   `apply`), never graph nodes.

4. **Fidelity is data.** Whether a conversion round-trips, and what happens
   to a symbol a table does not know, is queryable (`NOTATION_INFO`, the
   `errors=` policy), not folklore buried in docstrings.

The core modules hold no pronunciation rules. Grapheme-to-phoneme inference
needs language knowledge beyond symbol tables, so it lives in the
`phonemizers` subpackage. It joins the graph as one more kind of edge, and
only when the caller asks for it.

## A guided tour of the modules

### What script is this? The `scripts` module

```pycon
>>> from scriptconv import detect_script, script_runs, lang_to_script, base_direction
>>> detect_script("Здравствуйте")
'Cyrl'
>>> script_runs("привет hello")
[('Cyrl', 'привет '), ('Latn', 'hello')]
>>> base_direction("مرحبا hello")
'mixed'
>>> lang_to_script("uzb_cyr")  # (ISO 639 codes, BCP-47 tags, _cyr/_lat variants)
'Cyrl'

```

The returned ISO 15924 tags are **stable API**: downstream code compares
against them directly. `script_runs` follows the UAX #24 model, so combining
marks and neutral characters attach to the run they qualify, and accented
Cyrillic never splits. Details: [docs/scripts.md](scripts.md).

### Same sounds, different symbols: the `notation` module

Nine phoneme notations transcode through an IPA hub: ARPABET, X-SAMPA,
Kirshenbaum, Lexique, Cotovía, RFE, Buckwalter to Arabic, and Halabi (the Nawar Halabi Arabic-Phonetiser notation, popularized by the mantoq package).

```pycon
>>> from scriptconv import convert, arpa_to_ipa, ipa_to_arpa
>>> convert("HH AH0 L OW1", "arpa", "ipa")
'həloʊ'
>>> convert("kˈæt", "ipa", "x-sampa")
'k"{t'
>>> arpa_to_ipa("HH AH0 L OW1", stress=True)
'həlˈoʊ'
>>> ipa_to_arpa("həlˈoʊ", stress=True)  # (exact round-trip)
'HH AH0 L OW1'

```

Two contracts make this trustworthy:

- **`errors=`, codecs-style.** Every converter takes
  `errors="pass" | "replace" | "strict" | "ignore"` for symbols outside its
  table. `"strict"` raises `UnknownSymbolError(symbol, position, notation)`.
  Strict drops no mark and accepts spaces, the Unicode White_Space
  characters. The defaults preserve each converter's long-standing behavior.

- **Stress is preserved, not discarded.** With `stress=True`, ARPABET stress
  digits become IPA `ˈ`/`ˌ` placed before the stressed vowel. This is
  reversible by construction, with no syllabification involved. Round-trips
  are exact up to IPA-equivalence. The
  [fidelity table](notation.md#fidelity-of-each-notation) states every residue.

Buckwalter is an independent implementation of the published transliteration
scheme, including alef wasla and the dagger alef (رحمٰن transliterates as
*rHm&#96;n*). The Halabi notation
is the phonetic alphabet of the Halabi Arabic-Phonetiser. Text in it
converts one way to IPA (`halabi_to_ipa("mrHbaa")` → `'mrħbaː'`) and onward
through the graph. Details: [docs/notation.md](notation.md).

### Rewriting the writing: `translit`, `readings`, `cangjie`

Deterministic, table-driven operations on the writing system itself:

```pycon
>>> from scriptconv import decompose_hangul, hira_to_kana
>>> decompose_hangul("한국")
'ㅎㅏㄴㄱㅜㄱ'
>>> hira_to_kana("こんにちは")
'コンニチハ'

```

Where a respelling needs a *dictionary*, because the answer is lexical and
not mechanical, it lives behind an extra and raises a clear `ImportError`
when the dictionary is not installed:

```pycon
>>> from scriptconv import to_hiragana, to_katakana, to_pinyin, to_bopomofo, to_cangjie
>>> to_hiragana("東京タワー")  # pip install scriptconv[ja]
'とうきょうたわー'
>>> to_katakana("日本語")
'ニホンゴ'
>>> to_pinyin("中国人")  # pip install scriptconv[zh]
'zhōng guó rén'
>>> to_bopomofo("中国")
'ㄓㄨㄥ ㄍㄨㄛˊ'
>>> to_cangjie("倉頡")  # vendored table, no extra
'oiar grmbc'

```

`readings.tokens()` exposes the per-token stream underneath, for consumers
that need word boundaries. The Cangjie table (103,601 glyphs) ships inside
the wheel, so shape-code conversion needs no download and no dependency.
Details: [docs/translit.md](translit.md),
[docs/readings.md](readings.md).

### Marked or unmarked: the `conventions` module

A convention is a decoration a script's orthography can carry or omit. Each
one declares its *styles* and the transitions between them. `strip`/`apply`
are sugar for transitions to and from `"none"`.

```pycon
>>> from scriptconv import strip, restyle, detect_convention, conventions_for
>>> strip("مُحَمَّد", "tashkeel")
'محمد'
>>> strip("שָׁלוֹם", "niqqud")
'שלום'
>>> strip("わたし は がくせい です", "wakachigaki")
'わたしはがくせいです'
>>> restyle("zhōng guó", "pinyin-tone", "number", frm="mark")
'zhong1 guo2'
>>> detect_convention("مُحَمَّد", "tashkeel")
'marked'
>>> [c.id for c in conventions_for("Arab")]
['tashkeel', 'kashida', 'quranic-marks']

```

The registered set covers Arabic `tashkeel`, `kashida`, and `quranic-marks`;
Hebrew `niqqud` and `teamim` (vocalization and cantillation are separate
layers); Japanese `wakachigaki` (spacing is stripped only between Japanese
characters, so "きょうは good day" keeps its space); `pinyin-tone` (mark,
number, or none, deterministic both ways for standard apostrophized
pinyin); and `jamo-form` (compatibility or conjoining repertoires).

Which transitions exist follows one criterion. Stripping and deterministic
re-spelling are always available. Transitions that need a dictionary lookup
(applying wakachigaki means word segmentation) sit behind an extra.

Transitions that need contextual *prediction* (restoring tashkeel) are out
of scope entirely, because that is diacritization, a modelling problem. Their
absence is queryable data rather than a runtime surprise.

The codepoint sets are curated, not naive. Stripping tashkeel **excludes**
U+0653 to U+0655, because in decomposed text those combining marks *are* the
letters آ/أ/إ. A blanket strip would corrupt the consonantal skeleton.
Details: [docs/conventions.md](conventions.md).

### One graph over everything: the `graph` module

Every notation and orthography is a node. Every converter is an edge.
Routing finds the cheapest path and prefers lossless edges, so a lossless
two-hop route beats a lossy shortcut:

```pycon
>>> from scriptconv import DEFAULT_GRAPH
>>> DEFAULT_GRAPH.convert("こんにちは", "hira", "kana")
'コンニチハ'
>>> [f"{e.src}->{e.dst}" for e in DEFAULT_GRAPH.route("arpa", "x-sampa")]
['arpa->ipa', 'ipa->x-sampa']

```

Edges are `fn(text, **context)`. Routing context such as `lang=` passes
through opaquely.

Extension is explicit: `graph.extend(register_fn)` returns an extended copy,
and a graph's contents never depend on what happens to be installed.
`DEFAULT_GRAPH` itself contains only orthographic and notation edges.
Details: [docs/graph.md](graph.md).


### From spelling to sound: the `phonemizers` module

The `phonemizers` subpackage wraps grapheme-to-phoneme engines behind one
interface. Some engines ship inside scriptconv: dizione, Leokani G2P, g2pW,
the kolokwa reader, the Vosk Russian rules, the Shami frontend and the Kabyle
Matoub rules. Most others come from the package that an extra installs.
Each language has a default backend, and `override=` picks another one:

```pycon
>>> from scriptconv.phonemizers import phonemize, Phonemizer
>>> phonemize("kaixo mundua", "eu")  # (euskaphone)
'kai̯ˈʃo munˈdua'
>>> phonemize("hello", "en", override=Phonemizer.GRUUT)
'hɛlˈoʊ'

```

The default for a language comes from an explicit chain first: Arabic to
arbtok, Basque to euskaphone, Mirandese to its orthography2ipa specs,
Portuguese to tugaphone, Hebrew to phonikud and Liberian English (`lir`) to
kolokwa. Galician goes to Cotovía and
Russian to vosk only when their own notations are requested. Without an
explicit entry, orthography2ipa serves every language it has a spec for, and
espeak is the last resort. Arabic never falls back past arbtok.

Every backend imports lazily. A missing package raises an `ImportError` that
names the extra to install. [docs/backends.md](backends.md) lists every
backend, its class and its extra.

Phonemization joins the graph only on request:

```pycon
>>> from scriptconv import DEFAULT_GRAPH, phonemizers
>>> g = DEFAULT_GRAPH.extend(phonemizers.register)
>>> g.convert("bom dia", "text", "ipa", lang="pt")
'ˈbõ ˈdiɐ'
>>> g.can_convert("text", "arpa")  # (chains through IPA)
True

```

Diacritization restores marks that ordinary spelling leaves out but a
phonemizer needs. `scriptconv.diacritics.diacritize(text, lang)` adds Hebrew
niqqud (phonikud, `he`), Arabic tashkeel (text2tashkeel, `tashkeel`), word
stress for the languages stressonnx covers (`stress`) and European Portuguese
homograph marks (bifonia, `pt`):

```pycon
>>> from scriptconv.diacritics import diacritize
>>> diacritize("Tenho muita sede hoje.", "pt")
'Tenho muita sêde hoje.'

```

A voice reads text through `scriptconv.frontend.TextFrontend`. It splits out
inline `[[phoneme]]` blocks, runs the optional normalisation hook, cuts
sentences, then diacritizes and runs the backend per sentence. A backend that
runs a stage itself is not given that stage twice:

```pycon
>>> from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
>>> frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.ESPEAK))
>>> frontend.phonemize("Tenho sede [[ˈsedɨ]]. Olá!", Stages(diacritize=True))
[['t', 'ˌ', 'e', 'ɲ', 'ʊ', ' ', 's', 'ˈ', 'e', 'd', 'ɨ', ' ', 'ˈ', 's', 'e', 'd', 'ɨ'], ['ɔ', 'l', 'ˈ', 'a']]

```

Three rules hold for every backend:

- **scriptconv does not normalise text.** Pass `normalizer=`, a
  `(text, lang) -> str` callable, to run your own normaliser in the pipeline.
  `scriptconv.frontend.spoken_normalizer()` returns `text2spoken.normalize`
  for that hook, behind the `normalize` extra. Without a hook, the text is
  phonemized as written.
- **Some models download on first use, and others never do.** ByT5, Charsiu
  and phonetisaurus need a local `model=` path. These download on first use:
  the phonikud and Nakdimon Hebrew diacritizers, the fp32 text2tashkeel
  weights, the stressonnx models, the g2pW model, the Leokani G2P and
  kolokwa-g2p models, the two data files of the `nemo_ipa` backend and a named
  DeepPhonemizer checkpoint. The `g2pen` backend reads local NLTK data and
  downloads nothing. [docs/backends.md](backends.md#model-files) names
  each cache location.
- **orthography2ipa uses the packaged lexicons.** The `o2i` extra installs
  [o2i-lexicons](https://github.com/TigreGotico/o2i-lexicons), which holds
  the words that the orthography2ipa rules get wrong. Pass
  `packaged_lexicons=False` to `get_phonemizer` to use the rules only.

Details: [docs/phonemizers.md](phonemizers.md),
[docs/frontend.md](frontend.md).

## Related projects

phoonnx builds on scriptconv. scriptconv calls the other libraries below as
optional backends, and they work without scriptconv. pycotovia is the one
exception: its `alphabets` module imports scriptconv to convert its notation.

- [phoonnx](https://github.com/TigreGotico/phoonnx): multilingual ONNX
  text-to-speech. It takes its text path from scriptconv through
  `TextFrontend`.
- [text2spoken](https://github.com/TigreGotico/text2spoken): text
  normalisation, the `normalize` extra.
- [orthography2ipa](https://github.com/TigreGotico/orthography2ipa): a
  data-driven orthography-to-IPA engine, and the usual per-language default.
  Its specs give the Mirandese and Barranquenho backends.
- [arbtok](https://github.com/TigreGotico/arbtok),
  [euskaphone](https://github.com/TigreGotico/euskaphone) and
  [tugaphone](https://github.com/TigreGotico/tugaphone): the dialect-aware
  Arabic, Basque and Portuguese phonemizers.
- [pycotovia](https://github.com/TigreGotico/pycotovia): a pure-Python port
  of the Cotovía Galician TTS engine, whose notation scriptconv transcodes.
- [espyak](https://github.com/TigreGotico/espyak): a pure-Python port of the
  espeak-ng G2P, and the espeak fallback when the binary is absent.


---
[Home](index.md) · [Next →](install.md)
