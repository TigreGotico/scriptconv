# From spelling to sound — `scriptconv.phonemizers`

Everything else in scriptconv rewrites *symbols*. Phonemization answers a
different question — how text is *pronounced* — and that needs language
knowledge beyond symbol tables: pronunciation dictionaries, rule engines,
neural models. The core therefore contains no grapheme-to-phoneme rules at
all; this subpackage wraps real G2P **engines** behind optional extras, gives
every language a sensible default, and lets the caller override anything.

```python
from scriptconv.phonemizers import phonemize, Phonemizer

phonemize("kaixo mundua", "eu")                      # 'kai̯ʃo mundua'
phonemize("hello", "en", override=Phonemizer.GRUUT)  # a specific backend
```

## The contract

Every backend subclasses `BasePhonemizer` and speaks the same interface:

- `phonemize_string(text, lang) -> str` — the raw phoneme string.
- `phonemize(text, lang) -> list[list[str]]` — sentence-chunked phoneme
  lists, with a lazy variant (`phonemize_lazy`) that phonemizes one sentence
  at a time so a consumer can start on sentence one before sentence two is
  ready.
- `alphabet=` — the output symbol set, for engines that can emit more than
  one (`Alphabet.IPA`, `Alphabet.ARPA`, engine-native inventories).

**Normalization is injectable, not built in.** Speech pipelines expand
numbers, dates, and abbreviations before phonemizing ("call me at 5" should
not phonemize a digit); that requires language resources scriptconv does not
ship. Pass `normalizer=` — any `(text, lang) -> str` callable — and it runs
inside `phonemize_lazy`; without it, the raw text is phonemized as-is. A
pipeline that injects its own normalizer and one that doesn't will therefore
legitimately differ on text containing digits.

## The registry and per-language defaults

Every backend is a `Phonemizer` enum member whose string value is wire
format — configuration files store these strings, so they never change. The
registry maps each member to its module, class, and extra as *data*; classes
import lazily, and a missing backing package raises an `ImportError` that
names the extra to install. There are no silent gaps: every member either
resolves or explains itself.

`phonemizer_for_lang(lang, alphabet=Alphabet.IPA, override=None)` picks the
default, resolving in-house engines first:

1. the explicit per-language chain — Arabic → arbtok, Basque → euskaphone,
   Mirandese → mwl_phonemizer, Portuguese → tugaphone, Hebrew → phonikud,
   Galician → Cotovía (only when Cotovía's own notation is requested: a
   candidate must be able to *emit* the requested alphabet);
2. orthography2ipa, wherever it has a spec for the language;
3. espeak as the universal fallback (the espeak-ng subprocess, or the
   pure-Python espyak port when the binary is absent).

**Arabic never falls back.** If arbtok is ineligible or missing, resolution
raises instead of silently degrading to another engine — wrong phonemes are
worse than no phonemes.

## Joining the graph

Phonemization enters the [conversion graph](graph.md) only on request:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import phonemizers

g = DEFAULT_GRAPH.extend(phonemizers.register)
g.convert("bom dia", "text", "ipa", lang="pt")   # 'ˈbõ ˈdʒiɐ'
g.convert("hello", "text", "arpa", lang="en", override=Phonemizer.GRUUT)
```

`register` adds a `text` node — the context language's ordinary written form,
meaningful only with `lang=` — and one dispatching edge that resolves the
per-language default (or the `override=` context key). `DEFAULT_GRAPH` itself
stays free of sound-producing edges.

## Pre-G2P diacritics — `add_diacritics`

Some languages need pronunciation disambiguated *before* G2P runs, because
ordinary orthography drops information a downstream G2P engine depends on.
`BasePhonemizer.add_diacritics(text, lang, model=None)` wraps
four such backends, each lazy-imported and each raising a named
`ImportError` when its extra is missing:

| Language(s) | Backend | Extra | What it restores |
|---|---|---|---|
| `he` | phonikud (`phonikud_model=`) | `he` | niqqud |
| `ar` | text2tashkeel | `tashkeel` | tashkeel (+ hamza, dagger alef) |
| 26 stressonnx tags (`STRESS_LANGS`): East Slavic (`ru`, `uk`, `be`), Bulgarian/Macedonian/Slovene (`bg`, `mk`, `sl`), Latvian (`lv`), Armenian (`hy`), Georgian (`ka`), Turkic/Caucasian (`az`, `ba`, `cv`, `kbd`, `kjh`, `kk`, `ky`, `mdf`, `myv`, `sah`, `tg`, `tt`, `udm`, `uz`, `xal`) | stressonnx | `stress` | word stress |
| `pt` / `pt-PT` (not `pt-BR`) | bifonia | `pt` | heterophonic-homograph sense diacritics |

Stress is free and either unwritten or under-marked in all of these
languages. East Slavic is the clearest case: stress is also mobile (it
shifts between forms of the same word), and unstressed vowels reduce
(Russian о→[ɐ]/[ə] depending on distance from the stress), so a wrong or
missing mark corrupts the vowel quality of the whole word, not just its
prosody. The other families don't necessarily reduce vowels but still need
the mark for correct stress placement. stressonnx marks the stressed vowel
with a combining acute (U+0301); `az` and `uz` have Cyrillic/Latin script
variants (e.g. `az-Latn`) routed by the full tag, which is passed straight
through so stressonnx can pick the right one. stressonnx is not yet
published to PyPI, so `scriptconv[stress]` installs from source. European
Portuguese has heterophonic homographs whose pronunciation
depends on meaning (*sede* "thirst" → closed *sêde*, *sede* "seat" → open
*séde*); bifonia rewrites these with an explicit open/closed-vowel diacritic.
These are ordinary Portuguese orthographic marks, chosen so any downstream
G2P — rule-based, neural, or espeak — reads them correctly. It is
deliberately scoped to European Portuguese — Brazilian Portuguese's vowel
system differs, and `add_diacritics`
routes `pt-BR` straight through unchanged. Language routing for the two new
backends matches on the primary subtag exactly (not a prefix check), so e.g.
Berber (`ber`) never false-matches Belarusian (`be`).

Diacritization is also exposed as a graph transform, via
`scriptconv.diacritics.register` — parallel to the phonemization edge above,
it adds a lang-contextual `text-diacritized` node and two edges: `text ->
text-diacritized` (restore, wrapping `add_diacritics`, model-based and
expensive) and `text-diacritized -> text` (strip, cheap and lossless). Strip
removes only the specific overlay codepoints each backend adds — combining
acute/grave for stress, tashkeel for Arabic, niqqud for Hebrew — never a
blanket combining-mark filter, so precomposed native letters (Cyrillic й/ё,
Latvian macrons, Azerbaijani ç/ö, Arabic hamza carriers) are left intact.
That cost asymmetry is why routing never takes the round trip unless asked.
Strip only works for *overlay* diacritics — Arabic/Hebrew vocalization and
East-Slavic/Turkic/Caucasian stress, whose bare form carries no marks, gated
by exact primary-subtag match — and raises `ValueError` for languages where
the marks are native orthography (European Portuguese/bifonia), since
removing them would corrupt the spelling:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import diacritics

g = DEFAULT_GRAPH.extend(diacritics.register)
g.convert("Tenho muita sede hoje.", "text", "text-diacritized", lang="pt")
# 'Tenho muita sêde hoje.'
g.convert("за́мок", "text-diacritized", "text", lang="ru")   # 'замок'
g.convert("sêde", "text-diacritized", "text", lang="pt")     # raises ValueError
```

`add_diacritics` remains the single dispatch point — the graph edge is a thin
wrapper, not a second implementation.

## Model-backed engines never download

ByT5 and Charsiu run ONNX models. They require explicit local paths —
`model=` and `tokenizer_config=` — and raise immediately when the files are
absent. Downloading and caching model files is deliberately the caller's
concern; the class constants document where the published models live.

## Licensing quarantine — `_vendored`

Two G2P implementations are unpublished upstream and carry licenses
incompatible with Apache-2.0 redistribution as part of this library's own
code, so they are vendored in an explicitly quarantined subpackage,
`scriptconv/phonemizers/_vendored/`, **under their own licenses**:

- `mantoq/` — the Halabi Arabic-Phonetiser pipeline; its phonetisation core
  is **CC BY-NC 4.0** (non-commercial). See `mantoq/LICENSE.md`.
- `kog2p/` — Korean G2P, **GPL-3.0**. See `kog2p/LICENSE.md`.

The quarantine's guarantees: nothing imports it at package import time —
using these backends is an explicit per-request opt-in that accepts the
subpackage's license; encumbered license headers exist nowhere else in the
tree; and both notices ship in the wheel. An externally installed `mantoq` or
`kog2p` package takes precedence over the vendored copy. Unencumbered
defaults exist for both languages (arbtok, g2pk) and are what the
per-language resolution selects.

`MantoqPhonemizer` preserves its long-standing contract, because published
models trained on mantoq phoneme sequences depend on it: the default
`alphabet=Alphabet.BUCKWALTER` returns the raw mantoq inventory (that
historical label persists; `Alphabet.MANTOQ` is the accurate alias), and
`Alphabet.IPA` converts through
[`mantoq_to_ipa`](notation.md) — the mantoq inventory is itself a first-class
notation, so its output participates in graph routing like any other.

## The backend catalog

Multilingual: espeak (subprocess with espyak fallback), gruut, goruut,
epitran, transphone, ByT5/Charsiu (ONNX), the misaki family (en/ja/zh/ko/vi).
Per-language: English (DeepPhonemizer, OpenPhonemizer, g2p_en), Japanese
(OpenJTalk, cutlet, pykakasi), Korean (g2pk, KoG2P), Chinese (jieba, g2pM,
xpinyin, pypinyin), Arabic (arbtok, mantoq), Hebrew (phonikud), Persian,
Vietnamese (viphoneme), Portuguese (tugaphone, barranquenho), Galician
(Cotovía), Basque (AhoTTS, euskaphone), Mirandese, Levantine Arabic/English
code-switching (shami — whose `phonemize_with_language_ids` also returns the
parallel per-phoneme language-ID stream), and orthography2ipa for its
data-driven language specs. Trivial built-ins that need no extra:
`GraphemePhonemizer` (normalized characters) and `UnicodeCodepointPhonemizer`
(codepoints as phonemes).
