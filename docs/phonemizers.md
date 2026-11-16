# From spelling to sound, `scriptconv.phonemizers`

Everything else in scriptconv rewrites *symbols*. Phonemization answers a
different question, how text is *pronounced*, and that needs language
knowledge beyond symbol tables: pronunciation dictionaries, rule engines,
neural models. The core therefore contains no grapheme-to-phoneme rules at
all, this subpackage wraps real G2P **engines** behind optional extras, gives
every language a sensible default, and lets the caller override anything.

```python
from scriptconv.phonemizers import phonemize, Phonemizer

phonemize("kaixo mundua", "eu")                      # 'kai̯ʃo mundua'
phonemize("hello", "en", override=Phonemizer.GRUUT)  # a specific backend
```

## The contract

Every backend subclasses `BasePhonemizer` and speaks the same interface:

- `phonemize_string(text, lang) -> str`, the raw phoneme string.
- `phonemize(text, lang) -> list[list[str]]`, sentence-chunked phoneme
  lists, with a lazy variant (`phonemize_lazy`) that phonemizes one sentence
  at a time so a consumer can start on sentence one before sentence two is
  ready.
- `alphabet=`, the output symbol set, for engines that can emit more than
  one (`Alphabet.IPA`, `Alphabet.ARPA`, engine-native inventories).

**Normalization is injectable, not built in.** Speech pipelines expand
numbers, dates, and abbreviations before phonemizing ("call me at 5" should
not phonemize a digit), that requires language resources scriptconv does not
ship. Pass `normalizer=`, any `(text, lang) -> str` callable, and it runs
inside `phonemize_lazy`, without it, the raw text is phonemized as-is. A
pipeline that injects its own normalizer and one that doesn't will therefore
legitimately differ on text containing digits. `TextFrontend` takes the same
callable as its `normalizer` hook and runs it in a fixed stage order, see
[frontend.md](frontend.md).

**A backend can own a stage.** The class attribute `owned_stages` names the
stages that a backend always runs itself, so a frontend skips them. The names
are `normalize` and `diacritize`. Tugaphone and Arbtok own `diacritize`. A
stage that a backend runs only with an optional dependency is not owned.

**A backend reports what produced its output.** `identity(lang)` returns a
frozen `PhonemizerIdentity` with the backend, the engine distribution, its
installed version and the resolved language. `differs_from(other)` names the
fields that changed, so a cached result can be checked against the engine
installed on the machine. `revision` comes first in the result. When both sides
hold the same `revision`, a `version` difference is not reported, because the
spec that gives the phonemes did not change. The class attribute
`engine_distribution` names the package that supplies the engine, and `None`
means the code is in this repository.

**Failures have types.** Each error below is a `FrontendError`, which is a
`ValueError`. `UnsupportedLanguageError` means the backend has no reading for
the language. `StageError` means a stage failed. `UnreadTextError` means text
stayed unread, and its `unread` attribute lists that text.
`ModelUnavailableError` means a model cannot load.

**Punctuation is opt-in.** By default no punctuation reaches the phonemes,
which is what every voice trained on scriptconv's output so far has learned.
Set `keep_punctuation = True` on the instance (or pass `keep_punctuation=True`
to `get_phonemizer`) to keep it the way Piper does: each clause is phonemized
on its own and followed by its symbol, `.` `?` `!` alone and `,` `:` `;`
followed by a space (Arabic `،` `؛` `؟` map to the same symbols). With the
flag set, `phonemize_to_list(text)` equals the sentences of `phonemize(text)`
joined, so a voice trains on the same sequence it is later fed. Backends that
override `phonemize_to_list` or `phonemize_lazy` keep their own output and
ignore the flag. In either mode `phonemize_to_list` never returns the newline
espeak-ng prints at a clause break.

## The registry and per-language defaults

Every backend is a `Phonemizer` enum member whose string value is wire
format, configuration files store these strings, so they never change. The
registry maps each member to its module, class, and extra as *data*, classes
import lazily, and a missing backing package raises an `ImportError` that
names the extra to install. There are no silent gaps: every member either
resolves or explains itself.

`phonemizer_for_lang(lang, alphabet=Alphabet.IPA, override=None)` picks the
default, resolving in-house engines first:

1. the explicit per-language chain (Arabic to arbtok, Basque to euskaphone,
   Mirandese to its orthography2ipa specs, Portuguese to tugaphone, Hebrew to
   phonikud, Galician to Cotovía, and Russian to vosk for their own notations, only
   when their own notation is requested: a candidate must be able to *emit*
   the requested alphabet)
2. orthography2ipa, wherever it has a spec for the language
3. espeak as the universal fallback (the espeak-ng subprocess, or the
   pure-Python espyak port when the binary is absent)

**Arabic never falls back.** If arbtok is ineligible or missing, resolution
raises instead of silently degrading to another engine, wrong phonemes are
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

`register` adds a `text` node, the context language's ordinary written form,
meaningful only with `lang=`, and one dispatching edge that resolves the
per-language default (or the `override=` context key). `DEFAULT_GRAPH` itself
stays free of sound-producing edges.

## Pre-G2P diacritics, `add_diacritics`

Some languages need pronunciation disambiguated *before* G2P runs, because
ordinary orthography drops information a downstream G2P engine depends on.
`BasePhonemizer.add_diacritics(text, lang, model=None)` wraps
four such backends, each lazy-imported and each raising a named
`ImportError` when its extra is missing:

| Language(s) | Backend | Extra | What it restores |
|---|---|---|---|
| `he` | phonikud (`phonikud_model=`), or Nakdimon with `diacritizer_model="nakdimon"` | `he` | niqqud, without the `\|` that phonikud writes after a prefix letter |
| Arabic in Arabic script, as linguatag reads the tag: `ar` with any region, the individual Arabic languages such as `arz`, `apc` and `ary`, and Hassaniyya `mey` (not `ar-Latn`, nor `acy` and `pga`, which CLDR writes in Latin script) | text2tashkeel; `waqf=True` gives the pausal form | `tashkeel` | tashkeel (+ hamza, dagger alef) |
| 26 stressonnx tags (`STRESS_LANGS`): East Slavic (`ru`, `uk`, `be`), Bulgarian/Macedonian/Slovene (`bg`, `mk`, `sl`), Latvian (`lv`), Armenian (`hy`), Georgian (`ka`), Turkic/Caucasian (`az`, `ba`, `cv`, `kbd`, `kjh`, `kk`, `ky`, `mdf`, `myv`, `sah`, `tg`, `tt`, `udm`, `uz`, `xal`) | stressonnx | `stress` | word stress |
| Tags at linguatag distance 0 from `pt-PT`: `pt`, `pt-PT`, `pt-Latn-PT`, `por`, and lects such as `pt-PT-x-porto` (not `pt-BR`, `pt-AO`, `pt-MZ`) | bifonia, which receives the full tag | `pt` | heterophonic-homograph sense diacritics |

phonikud is the Hebrew default. `diacritize(text, "he",
diacritizer_model="nakdimon")` uses Nakdimon instead (Gershuni and Pinter,
"Restoring Hebrew Diacritics Without a Dictionary", Findings of NAACL 2022).
Nakdimon predicts a vowel point, a dagesh and a shin or sin dot for each
letter. Text that already holds a vowel point, a dagesh or a shin or sin dot
stays as written. The code comes from Nakdimon. The code and the model are
under the MIT licence:

| File | Source | Revision | Size | Licence |
|---|---|---|---|---|
| `Nakdimon.onnx` | github.com/elazarg/nakdimon, `nakdimon/data/` | `5b73cdd6a43ad465faabc8c1118933592df356c8` | 21 MB | MIT |

Stress is free and either unwritten or under-marked in all of these
languages. East Slavic is the clearest case: stress is also mobile (it
shifts between forms of the same word), and unstressed vowels reduce
(Russian о→[ɐ]/[ə] depending on distance from the stress), so a wrong or
missing mark corrupts the vowel quality of the whole word, not just its
prosody. The other families don't necessarily reduce vowels but still need
the mark for correct stress placement. stressonnx marks the stressed vowel
with a combining acute (U+0301), `az` and `uz` have Cyrillic/Latin script
variants (e.g. `az-Latn`) routed by the full tag, which is passed straight
through so stressonnx can pick the right one. stressonnx is not yet
published to PyPI, so `scriptconv[stress]` installs from source. European
Portuguese has heterophonic homographs whose pronunciation
depends on meaning (*sede* "thirst" → closed *sêde*, *sede* "seat" → open
*séde*), bifonia rewrites these with an explicit open/closed-vowel diacritic.
These are ordinary Portuguese orthographic marks, chosen so any downstream
G2P, rule-based, neural, or espeak, reads them correctly. It is
deliberately scoped to European Portuguese, Brazilian Portuguese's vowel
system differs, and `add_diacritics`
routes `pt-BR` straight through unchanged. Hebrew and stress routing
matches on the primary subtag exactly (not a prefix check), so e.g.
Berber (`ber`) never false-matches Belarusian (`be`). Arabic and European
Portuguese routing asks linguatag, so Aragonese (`arg`) and Mapudungun
(`arn`) never route to tashkeel.

Diacritization is also exposed as a graph transform, via
`scriptconv.diacritics.register`, parallel to the phonemization edge above,
it adds a lang-contextual `text-diacritized` node and two edges: `text ->
text-diacritized` (restore, wrapping `add_diacritics`, model-based and
expensive) and `text-diacritized -> text` (strip, cheap). Neither edge is
lossless: strip maps a letter with a mark and the bare letter to one string. Strip
removes only the specific overlay codepoints each backend adds, combining
acute/grave for stress, tashkeel for Arabic, niqqud for Hebrew, never a
blanket combining-mark filter, so precomposed native letters (Cyrillic й/ё,
Latvian macrons, Azerbaijani ç/ö, Arabic hamza carriers) are left intact.
A cheapest path never visits a node twice, so routing never takes the round
trip unless asked.
Strip only works for *overlay* diacritics, Arabic/Hebrew vocalization and
East-Slavic/Turkic/Caucasian stress, whose bare form carries no marks, gated
by exact primary-subtag match, and raises `ValueError` for languages where
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

`add_diacritics` remains the single dispatch point, the graph edge is a thin
wrapper, not a second implementation.

### Stress marks and the backends that read them

stressonnx writes the stress mark U+0301 after the stressed vowel. A backend
reads the mark only in the languages that it declares in
`stress_mark_langs`, and `reads_stress_mark(lang)` gives the answer through
linguatag, so `ru-RU` matches `ru` and `uk` does not.

In a language that stressonnx marks and that the backend does not declare,
the backend removes U+0301 from its text before it reads it. Then the marked
text gives the same output as the plain text. The removal is in
`BasePhonemizer`, on every method that takes text, so a direct call and a
`TextFrontend` call give the same output. A text method must be an instance
method: a `staticmethod` or `classmethod` in its place raises `TypeError`
when the class is made.

linguatag matches the language to a stressonnx tag, the same way as the
declaration, so `rus` and `ukr` get the removal and `kk-Latn` does not. The
removal takes only a U+0301 after a vowel letter of the script that
stressonnx writes for the language: Cyrillic for `ru`, Latin for `lv` and
`sl`, Georgian for `ka`, Armenian for `hy`. Every other acute is spelling and
stays: in a language that stressonnx does not mark (`café` in `pt-PT`),
after a letter of another script (`café` in Russian text), and after a
consonant (the NFD Macedonian letters ѓ and ќ). The removal also keeps the
combining grave (U+0300).

In a language that stressonnx writes in Latin script (`lv`, `sl`, `az-Latn`
and `uz-Latn`, and bare `az` and `uz`), an NFD acute on a Latin vowel looks
the same as a stress mark, so the removal also takes it: an NFD `café` in
such a text becomes `cafe`.

A declaration comes from a probe, not from a guess. The probe reads each word
of a word list plain and marked, with each backend that loads and each
language that the backend serves. A language is declared only when the mark
moves the stress onto the marked vowel and changes nothing else:

```bash
python scripts/probe_stress_marks.py words.tsv --out cells.tsv
```

`words.tsv` has the columns `lang` and `marked`, one marked word per row.

| Backend | Reads U+0301 in |
| --- | --- |
| `vosk` | `ru` |
| `graphemes` | every language, as text: `stress_notation="acute"` keeps U+0301, `"plus"` writes `+` before the stressed vowel (`прив+ет`), `"none"` removes it |
| `unicode` | every language, as a codepoint |
| every other backend in scriptconv | none |

A backend in scriptconv-copyleft or scriptconv-nonfree declares its own
languages in the same attribute.

### Stress marks and goruut

`GoruutPhonemizer` removes the stress marks of the `STRESS_LANGS` languages,
the combining acute (U+0301) and grave (U+0300), before it calls goruut. It
uses `strip_diacritics`, so precomposed letters such as й, ё and ā stay.

goruut has no key that turns these marks into a stress symbol. In goruut
v0.8.0, the maps in `dicts/<lang>/language.json` for Russian, Bulgarian,
Macedonian, Kazakh, Armenian, Georgian, Slovene and Latvian have no key with
an acute or a grave. The Ukrainian map has one acute key and the Belarusian
map has three. Each gives a vowel without a stress symbol, for example `і́`
gives `ʲi`.

A stress mark that goruut does not map stays in the source script inside the
IPA, or moves the vowel to the front of the word. So with goruut, the stress
marks that `diacritize` adds for these languages have no effect.

Arabic tashkeel and Hebrew niqqud reach goruut unchanged, because goruut
reads them. In goruut v0.8.0, `dicts/arabic/language.json` has 154 keys with
tashkeel (U+064B to U+0652), and `dicts/hebrew3/language.json`, which goruut
uses for Hebrew, has 69 keys with niqqud. goruut reads `ثُبُوتٌ` as `θubuːt`
and the bare `ثبوت` as `fbuːt`. goruut does not map every letter and mark
pair, so some marked words keep an Arabic or Hebrew letter in the IPA.

## Model-backed engines: download policy

ByT5 and Charsiu run large, licensed ONNX models. They require explicit local
paths, `model=` and `tokenizer_config=`, and raise immediately when the
files are absent. Downloading and caching those model files is deliberately
the caller's concern, the class constants document where the published
models live.

Small, known-good, unencumbered models are the exception. The Hebrew
diacritizer (phonikud, see `diacritics.py`) auto-provisions its ONNX model
using only the stdlib (`urllib.request`) into a cache dir on first use:
`<base>/scriptconv/phonikud` where `<base>` is `$SCRIPTCONV_CACHE` if set,
else `$XDG_CACHE_HOME` (default `~/.cache`), and reuses it afterward. Pass
`phonikud_model=<path or zero-arg callable>` to override, e.g. on an
air-gapped host. (`en.py`'s DeepPhonemizer backend similarly fetches its own
model via the `dp` package, that fetch is DeepPhonemizer's, not scriptconv's,
but the net effect for a caller is the same, no local path required.)

The Nakdimon model follows the same rule. It goes into
`<base>/scriptconv/nakdimon`, from a fixed commit of its repository. The
model must have its pinned sha256 when it is downloaded and each time it
loads from the cache. A cached file that fails the check or does not load is
removed and downloaded again once. With no network and no model that passes
the check, `diacritize` raises `ModelUnavailableError`, which names the file
and the cause.

The g2pW backend gets its files through `huggingface_hub`, at a fixed
revision, into the shared Hugging Face cache. Each file must have its pinned
sha256. A cached file with another sha256 is downloaded again once, unless
the Hub is offline (`HF_HUB_OFFLINE`). With no copy that passes the check,
the backend raises `ModelUnavailableError`.

## g2pW, Mandarin pinyin symbols

`Phonemizer.G2PW` reads Mandarin with g2pW (Chen et al., "g2pW: A Conditional
Weighted Softmax BERT for Polyphone Disambiguation in Mandarin", INTERSPEECH
2022). A BERT model reads each polyphonic character in the context of its
sentence, and tables give the reading of the other characters. The model runs
on onnxruntime, with no torch. Simplified and traditional characters both
read. The converter comes from g2pW, and its numpy batches and prediction
loop follow Piper's torch-free port (`src/piper/g2pw_onnx.py` of
github.com/OHF-Voice/piper1-gpl at `d76f335`, Apache-2.0 as its header
states). Install the backend with `pip install scriptconv[zh-phonemizers]`.

The output alphabet is `Alphabet.PINYIN`. A syllable gives three symbols:
the initial, the final and the tone digit 1 to 5. A syllable with no initial
takes `Ø`, and a final writes ü as `v`. Five rows of the g2pW reading table
do not split into an initial and a final of `SYMBOLS`. `n` and `ê` give one
symbol, the syllable with its tone digit, such as `n2`. `hm`, `hng` and `ng`
give `h m`, `h ng` or `n g` and the tone digit, and `m`, `ng` and `g` are not
finals. A space and the marks
`。 . ？ ? ！ ! — … 、 ， , ： : ； ;` stay as symbols, so the backend ignores
`keep_punctuation`. A lowercase Latin letter that is also a symbol, such as
`a` or `b`, stays too. `phonemize_string` joins the symbols with a space.

```python
from scriptconv.phonemizers import Alphabet, Phonemizer, get_phonemizer

g2pw = get_phonemizer(Phonemizer.G2PW, Alphabet.PINYIN)
g2pw.phonemize("银行在哪里？", "zh")
# [['y', 'in', '2', 'h', 'ang', '2', 'z', 'ai', '4', 'n', 'a', '3', 'l', 'i', '3', '？']]
g2pw.phonemize("我要去行走。", "zh")
# [['w', 'o', '3', 'y', 'ao', '4', 'q', 'u', '4', 'x', 'ing', '2', 'z', 'ou', '3', '。']]
```

The backend does not read digits, and a digit gives no symbol. Numbers,
dates and units belong to the normalisation stage, which runs before the
backend. A letter that has no reading and is not a symbol, such as `İ`, `A` or
a Cyrillic letter, also gives no symbol. The backend logs a warning that
names each run of these characters:

```python
g2pw.phonemize("他跑了3000米，花了15分钟。", "zh")
# WARNING g2pW gives no symbol for '3000', '15' in '他跑了3000米，花了15分钟。'; numbers belong to the normalisation stage
```

With `strict=True` (`FrontendConfig.strict`, or the backend's `strict`
field), the backend raises `UnreadTextError` instead, and its `unread` field
holds the runs, here `('3000', '15')`. Punctuation that is not a symbol, such
as `《》`, gives no symbol and no warning.

| File | Source | Revision | Size | Licence |
|---|---|---|---|---|
| `g2pw.tar.gz`: the ONNX model, `config.py` and the character lists | Hugging Face dataset `rhasspy/piper-checkpoints`, `zh/zh_CN/_resources/` | `581dcfb1856912507627724d4ab2817a20e889ca` | 113 MB | MIT (dataset card); the g2pW weights are Apache-2.0 |
| `tokenizer.json` | Hugging Face model `google-bert/bert-base-chinese` | `8f23c25b06e129b6c986331a13d8d025a92cf0ea` | 269 KB | Apache-2.0 |
| Three reading tables, in the wheel | github.com/GitYCC/g2pW, `g2pw/` | `b9328ce8129c4717a70f16a2688542a0197541dd` | 1.9 MB | Apache-2.0 |

## dizione, American English

`Phonemizer.DIZIONE` reads American English text into IPA. The engine is
[dizione](https://github.com/n4ze3m/dizione), Apache-2.0. Its code is vendored
byte for byte under `scriptconv/phonemizers/_thirdparty/dizione/`, with its
licence and the upstream commit in `UPSTREAM.md`. dizione looks words up in a
dictionary built from CMUdict. It picks the reading of a homograph from the
words around it, and a small model guesses the words that the dictionary does
not have. Its own text rules read numbers, dates, money, units and
abbreviations.

```python
from scriptconv.phonemizers.dizione import DizionePhonemizer

dz = DizionePhonemizer()
dz.phonemize_string("You read it yesterday.", "en-US")  # 'juː ɹˈɛd ɪt jˈɛstɚdˌeɪ'
dz.phonemize_string("It costs $12.", "en-US")  # 'ɪt kˈɔsts twˈɛlv dˈɑːlɚz'
```

The built data (the dictionary, the alignment table, the model and the
homograph weights, 5.4 MB) ships in the wheel, in `_thirdparty/dizione/built/`,
the folder where dizione itself looks for it. The files are byte-identical
copies of the folder `phonemizer/` of `n4ze3m/tiny-voca` at revision
`e5f9b116`, and `DATA_DIR` names the folder. The backend needs no download and
works offline. Pass `data_dir=` to read another build from a directory. The
backend never reads the `DIZIONE_DATA` environment variable. The dictionary,
alignment table and model come from CMUdict (`LicenseRef-CMUdict`, in
`built/LICENSE.cmudict`). The homograph weights come from the Wikipedia
Homograph Data (Apache-2.0, in `built/LICENSE.homograph-data`), and most of
their pronunciations come from CMUdict.

dizione reads the text itself, so the backend owns the `normalize` stage,
and the frontend runs no normaliser before it. The backend's own methods and
`tokens()` read the text whole. `phonemize_lazy` ends a sentence where dizione
does, at `.`, `?` or `!`, and a full stop that dizione reads as part of an
abbreviation, as in `Mrs.`, ends no sentence. `TextFrontend.phonemize_flat`
also gives the text whole.

The IPA string has a space between two words and a stress mark directly
before its vowel, as dizione writes it. It has no control symbol (`<bos>`,
`<eos>`, `<pad>`, `<sp>`) and no punctuation, because `.` is the IPA syllable
break. A TTS engine that reads dizione's token ids needs more than the IPA
string, so `DizionePhonemizer.tokens(text)` returns dizione's own
`Phonemized` object unchanged: the symbols, the ids into
`dizione.symbols.SYMBOLS` and the stress of each symbol (0, 1 or 2).
`identity(lang)` puts dizione's build fingerprint in `revision`, so tokens
from two builds of code, tables or data never mix. When overrides take effect,
from `overrides=` or from `DIZIONE_OVERRIDES`, `revision` is the sha256 of
the fingerprint and of the overrides.

`overrides=` takes pronunciations that win over every other source, in
CMUdict notation or as phones with stress marks:
`DizionePhonemizer(overrides={"kubernetes": "k ˌuː b ɚ n ˈɛ ɾ iː z"})`. A
phone outside dizione's inventory raises `ValueError`.

Limits:

- `TextFrontend.phonemize` splits the text into sentences with quebra_frases
  before the backend reads it, so dizione reads each piece alone. When
  quebra_frases takes the full stop of an abbreviation as a sentence end, the
  words after it lose their context. `Prof. Close the door.` reads "close" as
  the verb (`klˈoʊz`), `Jan. 1, 2000` reads "one" and not "first", and
  `See p. 12.` reads the letter "p" and not "page". `tokens()`, the backend's
  own methods and `TextFrontend.phonemize_flat` read these texts whole and
  give `klˈoʊs`, `fˈɜːst` and `pˈeɪdʒ`.
- dizione reads American English only. A tag must resolve to `en-US`, or to
  a lect of it such as `en-US-x-nyc`. A bare `en` is British English by the
  default-region rule, so it is refused with `UnsupportedLanguageError`, like
  `en-GB` and every other region.
- dizione also reads the overrides file named by the environment variable
  `DIZIONE_OVERRIDES`, in every instance. Unset it to get only the overrides
  that you pass.
- About one unknown word in three that the model guesses has an error, and
  foreign names have the most.
- `keep_punctuation` has no effect: the IPA string has no punctuation, and
  `tokens()` has all of it.

## Backends in scriptconv-copyleft and scriptconv-nonfree

A wrapper moves out of scriptconv when its own code or a dependency of its
engine is under a copyleft or a non-commercial licence. A wrapper that only
starts a separate program stays: Shami starts the espeak-ng command.
Two sister packages hold those wrappers, and their vendored code, under the
licences of that code:

- **scriptconv-copyleft** holds KoG2P and the espeak, Cotovía, AhoTTS,
  transphone, misaki, g2pfa, g2pk and pykakasi wrappers, and the Japanese
  functions of `scriptconv.readings`.
- **scriptconv-nonfree** holds mantoq, iqra_phonetiser and their wrappers
  (Mantoq, Halabi, Iqra), and the viphoneme, africa-g2p and ghana-g2p
  wrappers.

The registry keeps every member and its extra. A moved member imports from
its sister package when it is resolved, and the extra that served it
installs that package, so `pip install scriptconv[espeak]` still gives the
espeak backend. Without the sister package, `get_phonemizer` raises an
`ImportError` that names the extra. scriptconv never imports a sister
package at package import time.

The old import paths, for example
`scriptconv.phonemizers.mul.EspeakPhonemizer`, give the class from the
sister package with a `DeprecationWarning` until the release that
`scriptconv.phonemizers._moved.REMOVAL_VERSION` names.

### africa-g2p and ghana-g2p

`africa_g2p` (`AfricaG2PPhonemizer`) and `ghana_g2p` (`GhanaG2PPhonemizer`)
live in scriptconv-nonfree. The `africa` extra installs africa-g2p
(AfriSpeech/africa-g2p) from PyPI, at 0.3.5 or later. The `ghana` extra
installs ghana-g2p (GhanaNLP/ghana-g2p) with the same africa-g2p floor.
ghana-g2p loads the same installed africa-g2p, so the two backends read the
same rule tables. `identity()` gives the africa-g2p version for
`africa_g2p` and the ghana-g2p version for `ghana_g2p`.

Each africa-g2p rule table records its source in a `confidence` field. The
values `omniglot`, `high`, `medium` and `hand-verified` mean a transcription
of an Omniglot chart or of Hartell (ed.), *Alphabets of Africa* (UNESCO,
1993). Both backends serve these tables by default.

They also serve the 5 `tts-reviewed` tables of africa-g2p 0.3.5 by default:
Dagbani, Ewe, Fante, Ga and Twi. Each is an Omniglot chart with corrections
that an LLM proposed, and no native speaker has checked the corrections. The
corrected Ewe table measures closer to WikiPron Ewe than the chart it
replaces: phoneme error rate 0.4690 against 0.4948 on 247 words.

Every other value is a draft. In africa-g2p 0.3.5, 352 tables are
`llm-draft`: an LLM drafted them from corpus text, and no chart backs them.
Both backends refuse a draft table with `UnsupportedLanguageError`, and the
message names the table, its `confidence` and the africa-g2p version.
`allow_draft_rules=True` on the constructor, or as a keyword of
`get_phonemizer`, accepts the drafts:

```python
from scriptconv.phonemizers import Phonemizer, get_phonemizer

get_phonemizer(Phonemizer.AFRICA_G2P, allow_draft_rules=True).phonemize_string("aba", "aab")
```

The code of africa-g2p is Apache-2.0. Its rule tables have no licence grant,
and they are not for commercial use. scriptconv-nonfree states the terms in
`LICENSE.africa-g2p-data.md`.

### Three Arabic edges on the same Halabi phonetiser

`mantoq`, `halabi` and `iqra` share one backend — Nawar Halabi's
Arabic-Phonetiser (2016, CC BY-NC 4.0), vendored in scriptconv-nonfree or
installed as the `mantoq` package — at three different points in its
pipeline:

- `Phonemizer.MANTOQ` (`MantoqPhonemizer`): the full pipeline, mantoq's own
  diacritizer restoring tashkeel on bare text before the phonetiser runs.
  Preserves its long-standing contract, because published models trained on
  Halabi-notation phoneme sequences depend on it: the default
  `alphabet=Alphabet.BUCKWALTER` returns the raw inventory (that historical
  label persists — `Alphabet.HALABI` is the accurate name and returns the
  byte-identical string; there is no separate orthographic Buckwalter
  transliteration layer in this pipeline to distinguish it from, so
  `BUCKWALTER` is kept only as a back-compat alias, not because the label was
  ever meaningfully different), and `Alphabet.IPA` converts through
  [`halabi_to_ipa`](notation.md).
- `Phonemizer.HALABI` (`HalabiPhonemizer`): the phonetiser called directly,
  no diacritizer — **input must already be fully vowelized** (bare text is
  garbage in, garbage out, matching upstream). `Alphabet.HALABI` (default)
  is the raw notation verbatim, including the stress/vowel-realization digit
  suffix and the emphatic-context uppercase vowels mantoq's own
  `simplify_phonemes` folds away; `Alphabet.IPA` strips the digits and
  converts through `halabi_to_ipa`.
- `Phonemizer.IQRA` (`IqraPhonemizer`): the same direct-phonetiser call as
  `HALABI`, post-processed to match the IqraEval shared task's `phoneme_ref`
  convention (Interspeech 2025, doi:10.21437/Interspeech.2025-2411 — "we
  employed the phonetizer introduced by Nawar Halabi"). Three deterministic,
  tajwid/grammar-cited text transforms run before phonetisation (universal
  tanwin elision, wāw al-jamāʿah's silent alif, utterance-initial hamzat
  al-waṣl on the definite article); see `scripts/benchmark_iqraeval.py` for
  the verification methodology (77.6% exact token-match against a 2,588-row
  IqraEval/Iqra_train dev-split sample) and `IqraPhonemizer`'s docstring for
  the named residual divergence classes, most of which are bugs in the
  vendored phonetiser itself rather than gaps in this edge's post-processing.
  `Alphabet.IPA` converts through
  [`iqra_halabi_to_ipa`](notation.md), which — unlike `halabi_to_ipa` — keeps
  the emphatic-context vowels distinct, matching `phoneme_ref`'s own
  notation.

None of the three is selected automatically for any language;
`ArbtokPhonemizer` is the Arabic default (`LANG_DEFAULTS["ar"]`).

## The sentence gate

A frontend stage stays only when it makes the output better than
orthography2ipa alone. The module `scriptconv.testing.compare` measures this
for each stage. Install it with the `test` extra.

The input is a TSV sentence set with this header row:

```
id	lang	category	text	expected_ipa	source	tier
```

The category is `plain`, `number`, `date`, `abbreviation`, `homograph` or
`contact`. The tier is `gold` or `silver`.

Run the gate on one language:

```bash
python -m scriptconv.testing.compare --lang pt-PT \
    --tsv tests/data/sentences/pt-PT.tsv --backend tugaphone \
    --stages homographs:homograph
```

`--backend` takes a scriptconv phonemizer name, or `module:attribute` for
your own backend. Each item of `--stages` is a stage name and the category
that the stage must improve.

The gate counts the phoneme error rate (PER) for each category. The PER is
the edit distance from the backend output to `expected_ipa`, divided by the
segment count of `expected_ipa`.

A stress mark is one segment, because stress changes what a voice says.
Spaces, syllable marks and tie bars are not segments, so `t͡s` and `ts` are
the same. This is a known limit: the PER cannot tell an affricate from a stop
followed by a fricative, such as Polish `czy` [t͡ʂɨ] and `trzy` [tʂɨ].

The gain of a stage is the PER without the stage minus the PER with it. A
positive gain is good.

A stage passes when both of these are true:

- In its own category, the gain is more than the noise. The noise is the
  largest error change in one row, between the backend with the stage and
  the backend without it, divided by the segment count of the category. So a
  gain passes only when more than one sentence carries it. A homograph stage
  that fixes one vowel in each of 30 sentences passes. A stage that fixes
  five segments in one sentence does not pass.
- In each other category, the loss is one segment at most: the gain is at
  least minus 1 divided by the segment count of that category. An ablation
  is deterministic, so a larger loss is real harm. A stage that deletes one
  sentence in another category fails.

To switch a stage off, the gate calls `backend.without(stage)`. This method
returns the same backend without that stage. When a backend has no `without`
method, the gate prints `not ablatable` for each stage.

The output gives the rows read, scored and skipped, with the reason for
each skip. A row of another language is a filter. These rows are defects,
and the gate fails:

- A row with a wrong column count, an unknown category or an unknown tier.
- A row with an empty `text`, or an `expected_ipa` with no segments.
- A row with the `id` or the `text` of an earlier row. A repeated sentence
  would count as many sentences and loosen the noise of its category.

Give `--allow-skips` to score the other rows.

The gate scores gold rows and silver rows apart, and puts the tier at the
start of each line. Only gold rows decide the exit status. The last line is
`gate: PASS` or `gate: FAIL` with the reasons. The exit status is 1 when one
of these is true:

- A gold verdict fails.
- A gold stage is not ablatable, or has no gold rows in its own category.
- `--stages` is empty, or the set has no gold rows.
- The gold `full_vs_o2i` of a category is negative, so the backend is worse
  than orthography2ipa alone.
- A row has a defect and `--allow-skips` is not given, or no row is scored.

The exit status is 2 for a usage error, such as a missing file, a wrong
header, an unknown backend or an unknown stage.

## Shami: the 88- and 90-symbol inventories

The Shami front end for Levantine Arabic and English is vendored from
Al-aminI/hams-levantine-tts under Apache-2.0. Upstream has two symbol
inventories, and the ids of a model come from one of them. The caller states
the inventory with the `inventory` parameter of `ShamiPhonemizer` or of the
vendored `TextFrontend`. The value is the symbol count of the model.

| `inventory` | Source commit | Symbols |
| --- | --- | --- |
| `88` (default) | d7a3602 | The single-speaker inventory. |
| `90` | 80d79d0 | The 88 symbols, then `sil` (id 88) and `brk` (id 89). |

With `inventory=90` the front end reads pauses from punctuation. A run of
`, ; :` becomes `sil`, and a run that holds `. ! … —` becomes `brk`. Each mark of
a spaced run such as `. . .` gives its own `brk`. At a switch between Arabic and
English, a pause takes the place of the word boundary. The front end
removes these marks before G2P, so the next word can match the lexicon. A
question mark, `?` or `؟`, gives no pause and stays on the word.

The espeak reduced vowel `ᵻ` becomes `ə` in the 90 inventory and `<unk>` in the
88 inventory. The upstream tokeniser also reads the IPA letters `s i l` and
`b r k` as the pause symbols. The 90 inventory keeps this behaviour, so its ids
match upstream. Any other value of `inventory` raises `ValueError`, also
`88.0`, `True` and `"88"`.

```python
from scriptconv.phonemizers.shami import ShamiPhonemizer, SYMBOL_TO_ID_90

phonemizer = ShamiPhonemizer(inventory=90)
phonemes, lang_ids = phonemizer.phonemize_with_language_ids("شو، هلق.", "ar")
# phonemes[0] holds 'sil' after the comma and 'brk' after the full stop
ids = [SYMBOL_TO_ID_90[p] for p in phonemes[0]]
```

`SYMBOL_TO_ID`, `ID_TO_SYMBOL`, `VOCAB_SIZE`, `tokenize_ipa` and `encode` hold
the 88-symbol tables. `SYMBOL_TO_ID_90`, `ID_TO_SYMBOL_90` and `VOCAB_SIZE_90`
hold the 90-symbol tables, and `get_inventory(90)` gives the tokeniser and the
fold map. The two front ends share no state, so one process can use both.

## The backend catalog

Multilingual: espeak (subprocess with espyak fallback), gruut, goruut,
epitran, transphone, ByT5/Charsiu (ONNX), the misaki family (en/ja/zh/ko/vi).
Per-language: English (DeepPhonemizer, OpenPhonemizer, g2p_en, dizione), Japanese
(OpenJTalk, cutlet, pykakasi), Korean (g2pk, KoG2P), Chinese (jieba, g2pM,
xpinyin, pypinyin, g2pW), Arabic (arbtok, mantoq), Hebrew (phonikud), Persian,
Vietnamese (viphoneme, Python below 3.12 only), Portuguese (tugaphone), Galician
(Cotovía), Russian (vosk, the vosk-tts inventory, `Alphabet.VOSK`, with the
voice's pronunciation dictionary passed as `phonemizer_model`), Basque
(AhoTTS, euskaphone), African languages (africa-g2p, ghana-g2p), Mirandese and Barranquenho (the orthography2ipa specs
`mwl`, `mwl-x-sendim`, `mwl-x-ifanes` and `ext-PT-x-barranco`), Levantine
Arabic/English code-switching (shami, whose `phonemize_with_language_ids` also returns the
parallel per-phoneme language-ID stream), and orthography2ipa for its
data-driven language specs. Trivial built-ins that need no extra:
`GraphemePhonemizer` (normalized characters) and `UnicodeCodepointPhonemizer`
(codepoints as phonemes).

The OpenJTalk backend runs on pyopenjtalk-plus with onnxruntime, which the
`ja-phonemizers` extra installs. pyopenjtalk installs the same `pyopenjtalk`
module with another dictionary and other accent rules, and pyopenjtalk-plus
without onnxruntime reads 何時 as なにじ. So the backend reads the RECORD of
each installed distribution and refuses, with an `ImportError` that names the
fix, an install where pyopenjtalk owns the module or where onnxruntime does not
import. The check is `scriptconv.phonemizers.openjtalk_engine.require_pyopenjtalk_plus`.
The pyopenjtalk-plus wheel holds the OpenJTalk dictionary, so the first use
needs no network.

pyopenjtalk reads the variable `OPEN_JTALK_DICT_DIR` when it imports, and uses
that dictionary in place of the bundled one. The readings then change while
the identity still names pyopenjtalk-plus. So the backend also refuses, with an
`ImportError`, a value of `OPEN_JTALK_DICT_DIR` that does not resolve to the
bundled dictionary:

```python
# OPEN_JTALK_DICT_DIR=/usr/share/open_jtalk/dic python
get_phonemizer(Phonemizer.OPENJTALK)
# ImportError: The OpenJTalk phonemizer reads the dictionary of pyopenjtalk-plus, but
# OPEN_JTALK_DICT_DIR names the dictionary /usr/share/open_jtalk/dic. Unset
# OPEN_JTALK_DICT_DIR, then start Python again.
```

See [ovos.md](ovos.md) for using this layer from OVOS through
`ovos-scriptconv-g2p-plugin`.

---
[← graph](graph.md) · [frontend →](frontend.md) · [Home](../README.md)
