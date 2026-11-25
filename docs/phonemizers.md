# From spelling to sound, `scriptconv.phonemizers`

<!-- agent-hint
covers: the BasePhonemizer contract, the registry and the language defaults, identity and revision, diacritize, stress marks, the model-backed engines, the sister packages and the sentence gate
source: scriptconv/phonemizers/base.py, registry.py, _revision.py, g2pw.py, lir.py, dizione.py, leokani.py, nemo_ipa.py, shami.py, f5tts.py; scriptconv/diacritics.py; scriptconv/testing/compare.py
generated: no
verify: python scripts/check_doc_page.py docs/phonemizers.md
see: docs/backends.md, docs/frontend.md, docs/graph.md
-->

This page tells how scriptconv turns text into phonemes, and what each
phonemizer backend gives. [backends.md](backends.md) lists every backend with
its class and its extra.

The other modules of scriptconv rewrite *symbols*. Phonemization tells how
text is *pronounced*, and that needs language knowledge: pronunciation
dictionaries, rule engines and neural models. The core holds no
grapheme-to-phoneme (G2P) rules. This subpackage wraps G2P **engines** behind
optional extras, gives each language a default backend, and lets the caller
choose another one.

```python
from scriptconv.phonemizers import phonemize, Phonemizer

phonemize("kaixo mundua", "eu")                      # 'kai̯ˈʃo munˈdua'
phonemize("hello", "en", override=Phonemizer.GRUUT)  # 'hɛlˈoʊ'
```

## The contract

Each backend subclasses `BasePhonemizer` and has the same methods:

| Name | Gives |
| --- | --- |
| `phonemize_string(text, lang) -> str` | The phoneme string of the whole text |
| `phonemize(text, lang) -> list[list[str]]` | One phoneme list for each sentence |
| `phonemize_lazy(text, lang)` | The same lists, one at a time, so a consumer can start on the first sentence before the next one is read |
| `phonemize_to_list(text, lang) -> list[str]` | The sentences of `phonemize_lazy` joined in one list |
| `alphabet=` | The output symbol set, for an engine that can write more than one (`Alphabet.IPA`, `Alphabet.ARPA` or a notation of the engine) |

**Normalisation is a hook.** A speech pipeline writes numbers, dates and
abbreviations as words before G2P, so that "call me at 5" does not reach the
backend as a digit. That needs language resources that scriptconv does not
ship. Pass `normalizer=`, a `(text, lang) -> str` callable, and
`phonemize_lazy` runs it first. Without it, the backend reads the text as
written. So a pipeline with a normaliser and one without it give different
phonemes for text with digits. `TextFrontend` takes the same callable as its
`normalizer` hook and runs it in a fixed stage order, see
[frontend.md](frontend.md).

**A backend can own a stage.** The class attribute `owned_stages` names the
stages that a backend always runs itself, so a frontend skips them. The names
are `normalize` and `diacritize`. Tugaphone owns `normalize` and `diacritize`,
euskaphone owns `normalize`, and Arbtok owns `diacritize`. A
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

**Each backend holds a `revision`.** For `graphemes`, `unicode` and
`matoub_kab`, the `revision` is `sc2:` and a hash of the code and data on the
path of the backend. `dizione` takes it from its engine.

For `tugaphone`, `orthography2ipa`, `mwl_phonemizer` and `barranquenho`, the
`revision` is `sc2:` and a hash of the revision that the engine gives and of
the code on the path of the backend. The engine revision is
`tugaphone.revision(lect)` or the orthography2ipa spec revision of the lect,
with its packaged lexicon. The files of the distributions that the engine
revision covers leave the hash. So an engine release that keeps its revision
keeps the `revision` of the backend, and a change of the scriptconv code on
the path changes it. When the engine gives no revision, with one warning, or
when the tugaphone `contact` is not `none`, the `revision` holds the engine
version in place of the engine revision, as for the other engines below.

For a backend that calls any other engine, such as `epitran`, `espeak` or
`gruut`, the `revision` is `sc2:` and a hash of the engine name and version and
of the code on the path of the backend. For `espeak` the version is the version
of the espeak-ng binary. So an engine release changes the `revision`, and so
does a change of the scriptconv code on the path or a release of quebra-frases.
The wrappers in scriptconv-copyleft and scriptconv-nonfree are code on the path.

The hash covers these inputs:

- each module of scriptconv, scriptconv-copyleft and scriptconv-nonfree that
  the backend class imports, directly or through another such module. The
  imports are read from the source, so a module counts whether or not a call
  reaches it.
- each other file in the directory of such a module, and in each directory
  under it that is not a package, such as the tables of a vendored engine. A
  package that loads only as the parent of such a module adds no files.
- the name and version of each installed distribution that the `phonemizers`
  extra and the extra of the backend require, at any depth, and those of the
  engine. A requirement under an extra counts only when that extra is asked
  for. The engine counts with its extra named by the language, when it has
  one, so `gruut` for `fr` counts `gruut-lang-fr`. A requirement for another
  platform or Python version does not count. The engine, and each
  distribution that an engine revision covers, count only once, in the
  settings.
- the name and version of each installed distribution that provides a module
  that the scriptconv modules above import at module level, in a `try` block
  or not, such as `num2words`, which the Shami normaliser uses when it is
  installed. The requirements of such a distribution do not count. A
  distribution that these modules import only inside a function does not
  count, unless an extra above requires it. So an optional tool that a backend
  loads inside a function is not in the `revision`. An example is the
  camel-tools diacritizer of the Shami backend: its install can change the
  phonemes of undiacritized Arabic and keep the `revision`.
- the source file of each class of the backend outside scriptconv, so a
  subclass counts
- the arguments of the backend, a character rule set on the instance, whether
  the backend keeps clause punctuation, the language and the Unicode version
  of Python

The code of a module counts as its tokens. Comments, blank lines, docstrings
and `version.py` do not count. A release of scriptconv that changes code or
data on the path of the backend changes the `revision`. A release that changes
only other backends, docs or `version.py` keeps it, and `differs_from` then
reports nothing. A release of a distribution in the list above changes the
`revision`, also when the phonemes stay the same, and a voice then warns once.
A release of any other distribution keeps the `revision`. This includes a
distribution that scriptconv imports only inside a function, and a
distribution that the engine loads at run time by a name that is not in the
scriptconv source, such as a model package, unless an extra of the backend
or of the engine requires it.

The hash reads no state of the running process: not the modules that it
loaded, not its working directory and not a package that loads at startup from
a `sitecustomize.py` or a `.pth` file. So two machines with the same packages
give the same `revision`. An edit of the files of a dependency that keeps its
version, as in an editable install, does not change the `revision`.

The code hash runs no process. It reads the source files on the path and the
installed metadata, and later calls in the process reuse the file digests.
`identity()` also reads the release of the engine, and the espeak backend
reads it from `espeak-ng --version` when it uses the binary. A
module of these packages that does not load from a file in a directory, such
as from a zip archive, gives no `revision`. So does a scriptconv with no
installed metadata. Each gives one warning per backend and language in a
process. A backend class that subclasses `BasePhonemizer` directly, outside
scriptconv and its sister packages, has no `revision`, because nothing names
the code on its path.

A `TextFrontend` has its own `revision`, which covers the frontend stages too.
See [frontend](frontend.md).

**Failures have types.** Each error below is a `FrontendError`, which is a
`ValueError`. `UnsupportedLanguageError` means the backend has no reading for
the language. `StageError` means a stage failed. `UnreadTextError` means text
stayed unread, and its `unread` attribute lists that text.
`ModelUnavailableError` means a model cannot load.

**Punctuation is opt-in.** By default no punctuation reaches the phonemes, and
the voices trained on that output learned none. Each sentence is then one list
of `phonemize(text)`: a `:`, `;`, `...` or `|` inside a sentence is a space, as
a `,` is. In Greek a `;` is the question mark, so it ends the sentence. The
tags `el`, `ell` and `gre` name Greek.

When punctuation is removed, a single hyphen between letters stays in the
word, as `flew-slowly` does. The Armenian hyphen (U+058A) and the Hebrew maqaf
(U+05BE) become that hyphen. A dash immediately between a letter and a letter
or digit gives a space, as `flew—slowly` gives `flew slowly`. Two or more
hyphens or dashes immediately between two letters or digits also give one
space. A dash run followed by punctuation or a combining mark does not give
that space.

Set `keep_punctuation = True` on the instance, or pass `keep_punctuation=True`
to `get_phonemizer`, to keep it as Piper does. Each clause is then phonemized
alone and followed by its symbol: `.` `?` `!` alone, and `,` `:` `;` followed
by a space. The Arabic `،` `؛` `؟` map to the same symbols. With the flag set,
`phonemize_to_list(text)` equals the sentences of `phonemize(text)` joined, so
a voice trains on the same sequence that it reads later. A backend that
overrides `phonemize_to_list` or `phonemize_lazy` keeps its own output and
ignores the flag. In either mode `phonemize_to_list` never returns the line
break that espeak-ng prints at a clause break.

## The registry and per-language defaults

Each backend is a `Phonemizer` enum member. Its string value is wire format:
configuration files store these strings, so they do not change. The registry
maps each member to its module, its class and its extra. A class imports only
when it is used, and a missing package raises an `ImportError` that names the
extra to install. So each member either resolves or tells why it cannot.

`phonemizer_for_lang(lang, alphabet=Alphabet.IPA, override=None, model=None)`
picks the backend for a language. `override=` always wins. Then it takes the
first of these that can write the requested alphabet:

1. The candidates of `LANG_DEFAULTS` for the primary subtag, in order:

   | Language | Candidates |
   | --- | --- |
   | `ar` | arbtok |
   | `eu` | euskaphone |
   | `mwl` | Mirandese, from its orthography2ipa specs |
   | `pt` | tugaphone |
   | `he` | phonikud |
   | `lir` | kolokwa |
   | `gl` | Cotovía, then orthography2ipa, then espeak |
   | `ru` | vosk, then orthography2ipa, then espeak |

   Cotovía writes only its own notation, and vosk only the vosk-tts
   inventory. So Galician and Russian take them only when the caller asks for
   that alphabet, and IPA goes to orthography2ipa.
2. orthography2ipa, for IPA, when it has a spec for the language.
3. espeak, the last resort: the espeak-ng program, or the pure-Python espyak
   port when the program is not installed.

**Arabic never falls back.** When no Arabic candidate can write the alphabet,
`phonemizer_for_lang` raises `ValueError`, and a missing arbtok raises
`ImportError`. Wrong phonemes are worse than no phonemes.

## Joining the graph

Phonemization enters the [conversion graph](graph.md) only when the caller
adds it:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import phonemizers

g = DEFAULT_GRAPH.extend(phonemizers.register)
g.convert("bom dia", "text", "ipa", lang="pt")   # 'ˈbõ ˈdiɐ'
g.convert("hello", "text", "arpa", lang="en", override=Phonemizer.GRUUT)  # 'HH EH L OW'
```

`register` adds the `text` node, the ordinary written form of the language
that the `lang=` context key names. It adds two edges, `text -> ipa` and
`text-diacritized -> ipa`. Each one phonemizes with the default backend of the
language, or with the `override=` backend, and takes the model from the
`phonemizer_model=` context key. The second example routes on from `ipa` to
`arpa` through the notation edges. `DEFAULT_GRAPH` itself holds no edge that
gives sound.

## Diacritics before G2P, `diacritize`

Some spellings leave out information that a G2P engine needs. The function
`scriptconv.diacritics.diacritize(text, lang="und", diacritizer_model=None, waqf=None)`
adds those marks before the backend reads the text. A phonemizer runs no
diacritizer itself: `TextFrontend` runs `diacritize` in its diacritize stage,
and the graph runs it on its `text -> text-diacritized` edge.

`diacritize` sends the text to one of four backends by the language. Each
backend loads only when it is used, and a missing one raises an `ImportError`
that names its extra. `phonikud_model=` and `model=` are other names of
`diacritizer_model`. Text in any other language comes back unchanged.

| Language | Backend | Extra | What it adds |
|---|---|---|---|
| `he` | phonikud, or Nakdimon with `diacritizer_model="nakdimon"` | `he` | niqqud, without the `\|` that phonikud writes after a prefix letter |
| Arabic in Arabic script, as linguatag reads the tag: `ar` with any region, the individual Arabic languages such as `arz`, `apc` and `ary`, and Hassaniyya `mey`. Not `ar-Latn`, and not `acy` and `pga`, which CLDR writes in Latin script | text2tashkeel; `waqf=True` gives the pausal form | `tashkeel` | tashkeel, hamza and dagger alef |
| The 24 primary subtags of `STRESS_LANGS`: `ru`, `uk`, `be`, `bg`, `mk`, `sl`, `lv`, `hy`, `ka`, `az`, `ba`, `cv`, `kbd`, `kjh`, `kk`, `ky`, `mdf`, `myv`, `sah`, `tg`, `tt`, `udm`, `uz` and `xal` | stressonnx | `stress` | word stress |
| Tags at linguatag distance 0 from `pt-PT`: `pt`, `pt-PT`, `pt-Latn-PT`, `por`, and lects such as `pt-PT-x-porto`. Not `pt-BR`, `pt-AO` or `pt-MZ` | bifonia, which receives the full tag | `pt` | sense marks on heterophonic homographs |

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

Stress is free in all of the stress languages, and their spelling writes it
seldom or never. In East Slavic, stress also moves between the forms of a
word, and an unstressed vowel reduces: Russian о is [ɐ] or [ə] by its distance
from the stress. So a wrong or missing mark changes the vowels of the whole
word, not only its stress. The other families need the mark for the place of
the stress. stressonnx writes a combining acute (U+0301) after the stressed
vowel. stressonnx serves 26 tags, because `az` and `uz` each have a Cyrillic
and a Latin model. The full tag, such as `az-Latn`, goes to stressonnx
unchanged, so it picks the right model. A bare `az` or `uz` names no model,
and its text comes back unchanged.

European Portuguese has heterophonic homographs: the meaning gives the
pronunciation (*sede* "thirst" is closed *sêde*, and *sede* "seat" is open
*séde*). bifonia writes an open or a closed vowel mark on these words. The
marks are ordinary Portuguese spelling, so any G2P engine reads them: a rule
engine, a neural model or espeak. Brazilian Portuguese has another vowel
system, so `diacritize` gives `pt-BR` text back unchanged.

Hebrew and stress routing compare the primary subtag exactly, so Berber
(`ber`) never matches Belarusian (`be`). Arabic and European Portuguese
routing ask linguatag, so Aragonese (`arg`) and Mapudungun (`arn`) never reach
tashkeel.

`scriptconv.diacritics.register` adds the same step to a graph. It adds the
lang-contextual node `text-diacritized` and two edges: `text ->
text-diacritized` runs `diacritize`, and `text-diacritized -> text` runs
`strip_diacritics`. Neither edge is lossless. The first one runs a model, and
strip maps a marked letter and its bare letter to one string. A cheapest route
never visits a node twice, so a route takes the round trip only when the
caller asks for `text-diacritized`.

Strip removes only the marks that a backend adds: the combining acute and
grave for stress, tashkeel for Arabic and niqqud for Hebrew. It does not
remove every combining mark, so precomposed letters stay: Cyrillic й and ё,
Latvian macrons, Azerbaijani ç and ö, and the Arabic hamza carriers. Strip
works only for these added marks. For a language with no added marks, such as
English, it raises `ValueError` saying that scriptconv has no overlay
diacritics. European Portuguese raises the same exception for a different
reason: there the marks are spelling:

```python
from scriptconv import DEFAULT_GRAPH
from scriptconv import diacritics

g = DEFAULT_GRAPH.extend(diacritics.register)
g.convert("Tenho muita sede hoje.", "text", "text-diacritized", lang="pt")
# 'Tenho muita sêde hoje.'
g.convert("за́мок", "text-diacritized", "text", lang="ru")   # 'замок'
g.convert("sêde", "text-diacritized", "text", lang="pt")     # ValueError: cannot strip diacritics for lang='pt'
```

The graph edge calls `diacritize`. It is not a second implementation.

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
| `f5tts_char`, `f5tts_pinyin` | every language, as a character of the text |
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

## Model-backed engines: who downloads the model

ByT5 and Charsiu run large ONNX models under their own licences. They need
local paths, `model=` and `tokenizer_config=`, and raise at once when the
files are not there. scriptconv never downloads them: the caller downloads
and caches the files, and the class constants name where the published models
are.

scriptconv downloads a small, public model on first use. The Hebrew
diacritizer (phonikud, in `diacritics.py`) downloads its ONNX model with the
standard library (`urllib.request`) into `<base>/scriptconv/phonikud`, and
reads it from there afterwards. `<base>` is `$SCRIPTCONV_CACHE` when it is
set, else `$XDG_CACHE_HOME`, else `~/.cache`. Pass `phonikud_model=` a path or
a zero-argument callable to use another model, for example on a host with no
network. The DeepPhonemizer backend in `en.py` downloads a checkpoint named in
`DeepPhonemizer.MODELS` into `~/.local/share/deepphonemizer`, so it needs no
local path either.

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
backend. Another number, such as `Ⅻ` or `½`, gives no symbol either, and nor
does a letter that has no reading: a Latin letter of either case (`ibm` and
`IBM` alike), `İ`, or a Cyrillic letter. The backend logs a warning that names
each run of these characters, and adds the note on the normalisation stage
when a run holds a number:

```python
g2pw.phonemize("他跑了3000米，花了15分钟。", "zh")
# [['t', 'a', '1', 'p', 'ao', '3', 'l', 'e', '5', 'm', 'i', '3', '，', 'h', 'ua', '1', 'l', 'e', '5', 'f', 'en', '1', 'zh', 'ong', '1', '。']]
```

The call logs this warning:

```text
g2pW gives no symbol for '3000', '15' in '他跑了3000米，花了15分钟。'; numbers belong to the normalisation stage
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

## Kolokwa, Liberian English

`Phonemizer.KOLOKWA` reads Liberian English (Kolokwa, ISO 639-3 `lir`) with
the kolokwa-g2p model of michsethowusu, a Forward Transformer of the
`phonemize` package, with a pronouncing dictionary of 12,006 words. It runs an
ONNX export of the model on onnxruntime, with no torch. It is the default for
`lir`. It does not read `en` or `en-LR`, so the default for those tags does
not change. Install it with `pip install scriptconv[lir]`.

```python
from scriptconv.phonemizers import phonemizer_for_lang

phonemizer_for_lang("lir").phonemize_string("da man dey go drink cold water", "lir")
# 'ðæ mæ̃n de ko tɹɪ̃ŋk ko wɔtə˞'
```

The text reads as `phonemize` 0.2.4 reads it, and the output is the same.
Each character that is not a letter, a digit, a space, a hyphen or one of
`().,:?!/–` goes, so an apostrophe goes. A digit stays in the text, but the
model has no symbol for it, so it gives no phonemes. The text splits at
spaces and at those marks, which stay in the output. A word that is not in the
dictionary splits at hyphens and before each inner capital, so `DIY` gives
`d-a-j`.

The model files must have their pinned sha256. With no network and no cached
copy that passes the check, the constructor raises `ModelUnavailableError`.

| File | Source | Revision | Size | Licence |
|---|---|---|---|---|
| `model.onnx`, `kolokwa.json` | Hugging Face model `TigreGotico/kolokwa-g2p-onnx`, the ONNX export of `michsethowusu/kolokwa-g2p` at `92ed3b721a4f80f98d5b741fdd16352ca320f121` | `3729a707e532ba2929c884288bacf5d5d76f7316` | 59 MB | MIT |

## dizione, American English

`Phonemizer.DIZIONE` reads American English text into IPA. The engine is
[dizione](https://github.com/n4ze3m/dizione), Apache-2.0. Its code is vendored
byte for byte under `scriptconv/phonemizers/_thirdparty/dizione/`, with its
licence and the upstream commit in `UPSTREAM.md`. dizione looks words up in a
dictionary built from CMUdict. It picks the reading of a homograph from the
words around it, and a small model guesses the words that the dictionary does
not have. Its own text rules read numbers, dates, money, units and
abbreviations. Install the backend with `pip install scriptconv[en-phonemizers]`,
which holds numpy for that model.

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
and the frontend runs no normaliser before it. The backend reads whole text
(`reads_whole_text`): `TextFrontend` gives it the whole text, and dizione cuts
its own output at its own marks. `phonemize_segments(text, lang)` gives one
segment per clause, with the mark that ends it and a `stress` stream in step
with its characters. A clause ends after a run of `, . ? ! ; :` that follows a
sound, and it ends a sentence when the run holds `.`, `?` or `!`. A full stop
that dizione reads as part of an abbreviation, as in `Mrs.`, ends nothing. A
closing bracket after the run, or a quotation mark that closes an open
quotation, stays with the clause that ends, and so does a clause mark after
it, as in `"Stop." .`, so no clause starts with a mark. A `!` or `?` between
two letters with no space after it, as in `Sim!Não!`, is no clause mark: the
backend reads it as a space, in `tokens()` too. A sentence that a blank line
follows ends a paragraph, unless dizione's own rules read the blank line away,
as in `Jan.\n\n5`. dizione reads a blank line as a space, so a blank line
after `:`, `;`, an ellipsis or a title ends no paragraph. With
`keep_punctuation`, the frontend writes the clause symbol of each mark.

`DizionePhonemizer(tokens=True)` changes `phonemize_segments` only: each
segment is then a clause of dizione's own tokens, with its own `<bos>` and
`<eos>`, its marks, and `ids` and `stress` streams. `TextFrontend.segments`
groups them into chunks of any size and removes the inner `<eos>` `<bos>`
pairs, so its sentence chunks equal `token_segments(text)`, and its `NONE`
chunk equals `tokens(text)`. An inline block goes inside the chunk's `<bos>`
and `<eos>`, with dizione's `<sp>` as its word break, as dizione reads a word
in the place of the block. `mark_symbols(marks)` gives the tokens that dizione
writes for a run of marks after a word, with their ids and stress: `…` for
`...`, `"` for `»`, and a repeated mark once. They are the tokens after the
word in dizione's own read of a word and the marks, because dizione reads
some runs alone as an emoticon: `;*` alone gives no token, and after a word it
gives `;`. The frontend writes them after a block, so `Wait [[ab]].` ends in
`a b . <eos>`, as `Wait cat.` ends in `k æ t . <eos>`. Without `tokens=True`
it returns `None`.

The IPA string has a space between two words and a stress mark directly
before its vowel, as dizione writes it. It has no control symbol (`<bos>`,
`<eos>`, `<pad>`, `<sp>`) and no punctuation, because `.` is the IPA syllable
break. A TTS engine that reads dizione's token ids needs more than the IPA
string, so `DizionePhonemizer.tokens(text)` returns dizione's own
`Phonemized` object unchanged: the symbols, the ids into
`dizione.symbols.SYMBOLS` and the stress of each symbol (0, 1 or 2).
`token_segments(text)` gives the same sequence cut into sentences, each with
its own `<bos>` and `<eos>`. Joined, with each inner `<eos>` `<bos>` pair and
its ids and stress removed, the sentences are `tokens(text)`.
`identity(lang)` puts dizione's build fingerprint in `revision`, so tokens
from two builds of code, tables or data never mix. When overrides take effect,
from `overrides=` or from `DIZIONE_OVERRIDES`, `revision` is the sha256 of
the fingerprint and of the overrides.

`overrides=` takes pronunciations that win over every other source, in
CMUdict notation or as phones with stress marks:
`DizionePhonemizer(overrides={"kubernetes": "k ˌuː b ɚ n ˈɛ ɾ iː z"})`. A
phone outside dizione's inventory raises `ValueError`.

Limits:

- The token sequence holds no spaces, so a closing quote and an opening quote
  look the same. The backend reads each `"` in the text: a `"` after a space
  opens a quotation, and any other closes one. For `'` it counts the marks,
  so a `'` that dizione keeps for an elision, as in `rock 'n' roll`, moves
  that count.
- dizione ends a sentence after each initial of a name: `J. R. R. Tolkien
  wrote it.` reads as four sentences. The words are right, but at `SENTENCE`
  size a voice speaks each initial as its own utterance, with a final fall.
  Use `PARAGRAPH` or `NONE` size for such text.
- dizione reads American English only. A tag must resolve to `en-US`, or to
  a lect of it such as `en-US-x-nyc`. A bare `en` is British English by the
  default-region rule, so it is refused with `UnsupportedLanguageError`, like
  `en-GB` and every other region.
- dizione also reads the overrides file named by the environment variable
  `DIZIONE_OVERRIDES`, in every instance. Unset it to get only the overrides
  that you pass.
- About one unknown word in three that the model guesses has an error, and
  foreign names have the most.
- A spelling longer than the longest word of the dictionary, 28 letters, is
  read in pieces. The backend cuts it into pieces of at most 28 characters,
  reads each piece as it reads a word, and joins the pieces with no space
  between them, as it joins the parts of a hyphenated word. Each piece keeps
  its own main stress. A hyphen, a mark and a part of a web address are
  separate words to dizione already, so they keep their reading, and so does
  every word of 28 letters or fewer. Without the bound, the unknown-word model
  reads the whole run and the aligner matches its letters to its phones with a
  table of one cell per letter and per phone, so a run of that length with no
  end exhausts the memory of the machine.
- `keep_punctuation` has no effect: the IPA string has no punctuation, and
  `tokens()` has all of it.

## Leokani G2P, American English

`Phonemizer.LEOKANI` reads American English text into the phoneme codes of
Kokoro and misaki. The engine is
[Leokani G2P](https://github.com/Milliwatt-Labs/leokani-g2p) by Milliwatt
Labs. Its code is MIT, and its model files are CC BY 4.0. The code is
vendored byte for byte under `scriptconv/phonemizers/_thirdparty/leokani/`,
with its `LICENSE`, its `NOTICE` and its source revision. Leokani G2P looks
each word up in its lexicon and guesses the other words with a
letter-to-sound model. A context model then picks how each word is said in
its clause. Install the backend with `pip install scriptconv[en-phonemizers]`,
which holds numpy, onnxruntime and huggingface_hub.

```python
from scriptconv.phonemizers import Phonemizer, get_phonemizer

leokani = get_phonemizer(Phonemizer.LEOKANI)
leokani.phonemize_string("The wind was cold, so we read inside.", "en-US")
# 'ðə wˈɪnd wʌz kˈOld, sˌO wi ɹˈid ɪnsˈId.'
leokani.phonemize("The wind was cold, so we read inside.", "en-US")[0][:8]
# ['ð', 'ə', ' ', 'w', 'ˈ', 'ɪ', 'n', 'd']
```

The output alphabet is `Alphabet.IPA`, with the codes that the `misaki_en`
backend writes: `A`, `I`, `O`, `W` and `Y` stand for the diphthongs eɪ, aɪ,
oʊ, aʊ and ɔɪ, and `ᵊ` and `ᵻ` for reduced vowels. A Kokoro voice reads these
codes as they are. `phonemize_string` returns the output of the engine
unchanged, with the punctuation that the text holds. `phonemize` and the
frontend remove the punctuation before the engine reads the text, as for
the other backends.

`model="mini"` loads the larger model, which reads names and rare words
better. `micro` is the default:
`get_phonemizer(Phonemizer.LEOKANI, model="mini")`.

The model files come from the Hugging Face Hub, at a fixed revision, into the
shared Hugging Face cache, from the upstream repository
`milliwattlabs/leokani-g2p` at revision `a819acc8`. Each file must have its
pinned sha256. A cached file with another sha256 is
downloaded again once, unless the Hub is offline (`HF_HUB_OFFLINE`). With no
copy that passes the check, the backend raises `ModelUnavailableError`.

| File | Source | Revision | Size | Licence |
|---|---|---|---|---|
| `leokani_g2p.py`, in the wheel | Hugging Face model `milliwattlabs/leokani-g2p`; the same file is `src/leokani_g2p/runtime.py` of github.com/Milliwatt-Labs/leokani-g2p at `df8bc119` (1.3.0) | `a819acc86471a04a01ba3d3f30f3765e4675c7ca` | 189 KB | MIT |
| `micro` model: the lexicon and three ONNX models | Hugging Face model `milliwattlabs/leokani-g2p` | `a819acc86471a04a01ba3d3f30f3765e4675c7ca` | 10.2 MB | CC BY 4.0 |
| `mini` model, in `mini/` | Hugging Face model `milliwattlabs/leokani-g2p` | `a819acc86471a04a01ba3d3f30f3765e4675c7ca` | 10.8 MB | CC BY 4.0 |

Credit the engine as: Leokani G2P by Milliwatt Labs (milliwattlabs.com).

The backend owns no stage, so the frontend runs its normalise stage first.
Leokani G2P then runs its own text rules on the result, which read numbers,
money, dates, times, units and web addresses. `identity(lang)` gives a
`revision` that hashes the code on the path of the backend, the vendored
engine with it. That code holds the model revision and the sha256 of each
model file, so another model gives another `revision`.

Limits:

- Leokani G2P reads American English only. A tag must resolve to `en-US`, or
  to a lect of it such as `en-US-x-nyc`. A bare `en` is British English by
  the default-region rule, so it is refused with `UnsupportedLanguageError`.
- The engine reads a number word with a hyphen, such as `ninety-nine`, as one
  word with one stress: `nˈIntinˈIn`. Its own text rules write `99` as two
  words, `nˈInti nˈIn`. A normaliser that writes hyphens, as text2spoken
  does, gives the first form.
- When the engine reads the digits itself, `at 14:30` reads as "fourteen
  thirty", and `fell to -5 degrees` reads the sign as "dash". Normalise such
  text first.

## NeMo IPA, American English

`Phonemizer.NEMO_IPA` gives the symbols that NVIDIA NeMo's English `IpaG2p`
gives to the Magpie TTS `english_phoneme` sub-tokenizer. A caller that
indexes an English Magpie voice maps each character of the string to a token
id. The backend follows NeMo at commit `fd6a8775` (tag v3.0.0) and needs no
NeMo or torch package. The module docstring of `scriptconv/phonemizers/nemo_ipa.py`
names the NeMo files, and `scriptconv/phonemizers/_thirdparty/nemo/NOTICE`
holds the credit that the Apache License asks for. Install the backend with
`pip install scriptconv[en-phonemizers]`.

```python
from scriptconv.phonemizers import Phonemizer, get_phonemizer

nemo = get_phonemizer(Phonemizer.NEMO_IPA)
nemo.phonemize_string("She read the lead sheet at the café.", "en-US")
# 'ˈʃi READ ðə LEAD ˈʃit ˈæt ðə kəˈfeɪ.'
```

A word of the dictionary gives its first pronunciation. A heteronym, such as
`read` and `lead` above, and a word that the dictionary lacks give upper-case
letters. A hyphen splits a word that the dictionary lacks, and each part is
looked up alone. A word with `'s` or `s` after a dictionary word takes `s`,
`z` or `ɪz`. An accent is removed first. Digits stay digits. The punctuation
of the vocabulary stays, and a character that the vocabulary lacks is dropped,
as in NeMo. A space stays, also two in a row, except at the end.
The output has no random choice: NeMo keeps a word as letters with a
probability only while it trains, and this backend has no such parameter.

The two data files come from the Hugging Face Hub, at a fixed revision, into
the shared Hugging Face cache, from `Phoonnx/magpietts-multi-357m-unicode` at
revision `a0e169ad`. They are the copies that the Magpie TTS checkpoint holds.
The dictionary is not byte-identical to the copy in the NeMo tree (sha256
`7ea5c4c2` against `dd0927ff`): the two differ only in the order of the two
readings of `A`, and the pin follows the checkpoint. Each file must have its
pinned sha256. Pass `dictionary=` or `heteronyms=` to read a local file
instead.

| File | Source | sha256 | Size |
|---|---|---|---|
| `ipa_cmudict-0.7b_nv23.01.txt` | `assets/tokenizer/dc7d60d6b15a4651b21c9ca2932b62c6_ipa_cmudict-0.7b_nv23.01.txt` | `7ea5c4c2c59cc780748b24d4ab60bd689779c4ac4ea7e27c0a8c3e20f300c0fa` | 3.1 MB |
| `heteronyms-052722` | `assets/tokenizer/61d57a4ccb064d1e8e3d9f871c571932_heteronyms-052722` | `b701909aedf753172eff223950f8859cd4b9b4c80199cf0a6e9ac4a307c8f8ec` | 1.6 KB |

The backend owns no stage. `identity(lang)` gives a `revision` that hashes the
code on the path of the backend and the sha256 of the two data files.

Limits:

- The backend reads American English only. A tag must resolve to `en-US`, or
  to a lect of it. A bare `en` is British English by the default-region rule,
  so it is refused with `UnsupportedLanguageError`.
- NeMo raises `IndexError` for any text whose kept symbols are only spaces,
  such as `½ ¼ ¾`. The backend gives an empty string.
- The backend does not write numbers, dates or symbols as words. Normalise
  such text first.
- `phonemize_string` returns the symbol string with its punctuation.
  `phonemize` and the frontend remove the punctuation before the backend
  reads the text.

## Backends in scriptconv-copyleft and scriptconv-nonfree

A wrapper is not in scriptconv when its own code or a dependency of its
engine is under a copyleft or a non-commercial licence. A wrapper that only
starts a separate program stays: Shami starts the espeak-ng command.
Two sister packages hold those wrappers, and their vendored code, under the
licences of that code:

- **scriptconv-copyleft** holds KoG2P and the espeak, Cotovía, AhoTTS,
  transphone, misaki, g2pfa, g2pk and pykakasi wrappers, the Lithuanian
  pitch-accent backend `espeak_lt_accent`, the Hebrew `hebrew_ipa`, Japanese
  `openjtalk_prosody` and Thai `tltk` backends, and the Japanese functions of
  `scriptconv.readings`.
- **scriptconv-nonfree** holds mantoq, iqra_phonetiser and their wrappers
  (Mantoq, Halabi, Iqra), and the viphoneme, africa-g2p and ghana-g2p
  wrappers.

The registry keeps every member and its extra. Such a member imports from
its sister package when it is resolved, and its extra installs that package,
so `pip install scriptconv[espeak]` gives the espeak backend. Without the
sister package, `get_phonemizer` raises an `ImportError` that names the
extra. scriptconv never imports a sister package when scriptconv itself
imports.

The import paths of these classes in scriptconv, for example
`scriptconv.phonemizers.mul.EspeakPhonemizer`, give the class from the
sister package with a `DeprecationWarning`. They stay until the release that
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
`get_phonemizer(Phonemizer.AFRICA_G2P, allow_draft_rules=True).phonemize_string("aba", "aab")`
gives `'a b a'` from the draft table of `aab`.

The code of africa-g2p is Apache-2.0. Its rule tables have no licence grant,
and they are not for commercial use. scriptconv-nonfree states the terms in
`LICENSE.africa-g2p-data.md`.

### Three Arabic edges on the Halabi phonetiser

`mantoq`, `halabi` and `iqra` read Arabic with Nawar Halabi's
Arabic-Phonetiser (2016, CC BY-NC 4.0). None of the three is a language
default: `ArbtokPhonemizer` is the Arabic default (`LANG_DEFAULTS["ar"]`).

`Phonemizer.MANTOQ` (`MantoqPhonemizer`) runs the mantoq pipeline: digits
become Arabic number words, and then the phonetiser runs. It uses an
installed `mantoq` package, else the copy vendored in scriptconv-nonfree.
The vendored copy runs no diacritizer, so give it text with tashkeel. The default `alphabet=Alphabet.BUCKWALTER` returns the
raw mantoq inventory, the notation that published models trained on.
`Alphabet.HALABI` is the accurate name, and it returns the same string. No
separate Buckwalter transliteration step is in this pipeline, so
`BUCKWALTER` is only a second name. `Alphabet.IPA` converts through
[`halabi_to_ipa`](notation.md).

`Phonemizer.HALABI` (`HalabiPhonemizer`) calls the phonetiser directly, with
no diacritizer. **The input must have full tashkeel.** Bare text gives wrong
output, as upstream does. `Alphabet.HALABI`, the default, is the raw notation
as written: the stress and vowel digit after a vowel, and the upper-case
vowels of an emphatic context, which mantoq's own `simplify_phonemes` folds.
`Alphabet.IPA` removes the digits and converts through `halabi_to_ipa`.

`Phonemizer.IQRA` (`IqraPhonemizer`) gives the `phoneme_ref` notation of the
IqraEval shared task (Interspeech 2025, doi:10.21437/Interspeech.2025-2411:
"we employed the phonetizer introduced by Nawar Halabi"). It runs a port of
the task's own phonetiser, `phonetiser/phonetise_Arabic.py` of
Iqra-Eval/MSA_phonetiser, which writes `phoneme_ref`. That port is vendored
apart from the mantoq copy that the other two edges use. Three text
transforms run before it, each cited to its tajwid or grammar rule in
`_iqra_preprocess`: tanwin goes everywhere, the silent alif of wāw
al-jamāʿah goes, and an utterance-initial hamzat al-waṣl on the definite
article reads as hamza with fatḥa. `scripts/benchmark_iqraeval.py` measures
exact token agreement with `phoneme_ref`, and its docstring gives the method
and the result: 2,544 of 2,588 rows of the dev split (98.3%) match exactly.
`Alphabet.HALABI`, the default, gives the cleaned tokens of `phoneme_ref`.
`Alphabet.IPA` converts through [`iqra_halabi_to_ipa`](notation.md), which
keeps the emphatic-context vowels apart, as `phoneme_ref` does.

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
    --tsv sentences.tsv --backend mypackage.frontend:backend \
    --stages homographs:homograph
```

`--backend` takes a scriptconv phonemizer name, or `module:attribute` for
your own backend. A backend is any object with a
`phonemize(text, lang) -> list[list[str]]` method. Each item of `--stages` is
a stage name and the category that the stage must improve.

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
method, the gate prints `not ablatable` for each stage. No backend in
scriptconv has `without`, so a stage gate needs a backend that you write, and
a scriptconv backend name gives only the comparison with orthography2ipa.

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
phonemes[0]  # ['<bos>', 'ʃ', 'ˈ', 'uː', 'sil', ' ', 'h', 'l', 'ʔ', 'brk', '<eos>']
[SYMBOL_TO_ID_90[p] for p in phonemes[0]]  # [1, 35, 18, 77, 88, 4, 37, 43, 50, 89, 2]
ShamiPhonemizer(inventory="88")  # ValueError: no Shami inventory has '88' symbols
```

`ShamiPhonemizer.phonemize_segments` gives one segment per sentence, with its
`<bos>` and `<eos>` (`bounded`) and the `language_ids` stream. Through
`TextFrontend.segments`, each chunk at every size has one `<bos>` and one
`<eos>`, and its language ids stay in step with its symbols. Where two
sentences join, a space with the language id 3 (`NEUTRAL`) comes between them,
as the front end writes it between two words.

`SYMBOL_TO_ID`, `ID_TO_SYMBOL`, `VOCAB_SIZE`, `tokenize_ipa` and `encode` hold
the 88-symbol tables. `SYMBOL_TO_ID_90`, `ID_TO_SYMBOL_90` and `VOCAB_SIZE_90`
hold the 90-symbol tables, and `get_inventory(90)` gives the tokeniser and the
fold map. The two front ends share no state, so one process can use both.

## F5-TTS text tokens

An F5-TTS voice reads the tokens that the inference code of its project gives,
from a vocabulary of characters. Two backends give those tokens. Each reads a
whole sentence with its capitals, quotes and every mark, so the frontend adds
no clause symbol and `keep_punctuation` changes nothing.

`Phonemizer.F5TTS_PINYIN` gives the tokens of `convert_char_to_pinyin` in
`src/f5_tts/model/utils.py` of SWivid/F5-TTS at commit `600e5fd`, which F5-TTS
v1 Base and its fine-tunes read. rjieba cuts the text into words. Each hanzi
gives a space and its pinyin syllable in the TONE3 style of pypinyin, with tone
sandhi. A syllable in the neutral tone has no digit, as `men` below shows.
Every other character stays as itself. `;` becomes `,`, and curly
quotes become straight quotes. A word of more than one ASCII character follows
a space, unless the token before it is a space, `:`, `'` or `"`. Install it
with `pip install scriptconv[zh-phonemizers]`.

`Phonemizer.F5TTS_CHAR` gives one token for each character. Habibi-TTS
(SWivid/Habibi-TTS at `9274498`) and SILMA TTS (silma-ai/silma-tts at
`2816b5a`) pass the text to the model as it is, so their voices read these
tokens.

```python
from scriptconv.phonemizers import Alphabet, Phonemizer, get_phonemizer

f5 = get_phonemizer(Phonemizer.F5TTS_PINYIN, Alphabet.UNICODE)
f5.phonemize_to_list("我们用iPhone打电话。", "zh")
# [' ', 'wo3', ' ', 'men', ' ', 'yong4', ' ', 'i', 'P', 'h', 'o', 'n', 'e', ' ', 'da3', ' ', 'dian4', ' ', 'hua4', '。']
```

`tests/data/f5tts_parity.jsonl` holds the tokens of the upstream functions for
151 texts, and the tests compare both backends with them. The port of
`convert_char_to_pinyin` carries the MIT licence of F5-TTS in
`scriptconv/phonemizers/_thirdparty/LICENSE.f5tts`.

## Backends with their own output

[backends.md](backends.md) lists every backend with its class, its extra and
its language default. Most backends give IPA. These give something else, or
need a note:

| Backend | Output |
| --- | --- |
| `openjtalk_prosody` | OpenJTalk IPA with the accent marks `↑ ↓ #` |
| `hebrew_ipa` | IPA with stress, from text that carries niqqud |
| `tltk` | Thai IPA with a tone digit for each syllable, in the `th` extra |
| `espeak_lt_accent` | Lithuanian espeak-ng IPA with the three pitch accents `ˈ`, `ˌ`, `ˋ` from the stress dictionary of Reginutė, in the `espeak` extra |
| `vosk` | The vosk-tts inventory, `Alphabet.VOSK`. The pronunciation dictionary of the voice goes in as `model=` |
| `shami` | Levantine Arabic and English IPA. `phonemize_with_language_ids` also returns a language id for each phoneme |
| `mwl_phonemizer`, `barranquenho` | The orthography2ipa specs `mwl`, `mwl-x-sendim`, `mwl-x-ifanes` and `ext-PT-x-barranco` |
| `viphoneme` | Vietnamese IPA, on Python below 3.12 only |
| `graphemes` | The normalised characters (`GraphemePhonemizer`), with no extra |
| `unicode` | The codepoints of the text (`UnicodeCodepointPhonemizer`), with no extra |

`hebrew_ipa` reads the niqqud that the text carries and adds none, so text
without niqqud gives no phonemes. Hebrew does not diacritize by default. A
caller with text without niqqud turns the diacritize stage on, for example
`frontend.phonemize(text, Stages(lang="he", diacritize=True))`, and the
phonikud model of the `he` extra then adds the niqqud.

`GraphemePhonemizer` keeps a hyphen between two letters as part of the word.
It takes its character rules as keyword arguments, so a voice can match the
text it trained on. `lowercase`, `in_word_chars`, `replace_chars` and
`drop_chars` each replace the class default when they are given, and the
identity revision then holds them. A voice whose training text had no hyphen
in a word sets `in_word_chars=""`, and every hyphen becomes a space:

```python
from scriptconv.phonemizers.base import GraphemePhonemizer

GraphemePhonemizer().phonemize_string("Ela mora em Vila-Real.", "pt")  # 'ela mora em vila-real.'
GraphemePhonemizer(in_word_chars="").phonemize_string("Ela mora em Vila-Real.", "pt")  # 'ela mora em vila real.'
```

The OpenJTalk backend runs on pyopenjtalk-plus with onnxruntime, which the
`ja-phonemizers` extra installs. pyopenjtalk installs the same `pyopenjtalk`
module with another dictionary and other accent rules, and pyopenjtalk-plus
without onnxruntime reads 何時 as なにじ. So the backend reads the RECORD of
each installed distribution and refuses, with an `ImportError` that names the
fix, an install where pyopenjtalk owns the module or where onnxruntime does not
import. The check is `scriptconv.phonemizers.openjtalk_engine.require_pyopenjtalk_plus`.
The pyopenjtalk-plus wheel holds the OpenJTalk dictionary, so the first use
needs no network. The backend writes kana or Hepburn romaji, so it takes
`Alphabet.KANA` or `Alphabet.HEPBURN`:

```python
from scriptconv.phonemizers import Alphabet, Phonemizer, get_phonemizer

get_phonemizer(Phonemizer.OPENJTALK, Alphabet.KANA).phonemize_string("何時ですか", "ja")  # 'ナンジデスカ'
```

pyopenjtalk reads the variable `OPEN_JTALK_DICT_DIR` when it imports, and opens
that dictionary in place of the bundled one at its first reading. The readings
then change while the identity still names pyopenjtalk-plus. So the backend
also refuses, with an `ImportError`, any value of `OPEN_JTALK_DICT_DIR` but the
absolute path of the bundled dictionary. The check compares the text of the
path, because pyopenjtalk opens the value later: a relative path, or a link to
the bundled dictionary, can point at another dictionary by then, so both are
refused. A path with a `..` component is refused too, because the system
applies `..` after it follows a link, so `/a/link/../b` can name a directory
that `/a/b` does not.

```bash
OPEN_JTALK_DICT_DIR=/usr/share/open_jtalk/dic python -c "
from scriptconv.phonemizers import Alphabet, Phonemizer, get_phonemizer
get_phonemizer(Phonemizer.OPENJTALK, Alphabet.KANA)"
```

```text
ImportError: The OpenJTalk phonemizer reads the dictionary of pyopenjtalk-plus, but OPEN_JTALK_DICT_DIR is '/usr/share/open_jtalk/dic', not '.../site-packages/pyopenjtalk/dictionary'. Unset OPEN_JTALK_DICT_DIR, then start Python again.
```

See [ovos.md](ovos.md) for using this layer from OVOS through
`ovos-scriptconv-g2p-plugin`.

---
[Index](index.md) · [← graph](graph.md) · [frontend →](frontend.md)
