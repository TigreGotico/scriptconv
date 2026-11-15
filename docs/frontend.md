# From text to phonemes, `scriptconv.frontend`

`TextFrontend` takes text to phonemes for a voice. It joins the text stages and
a phonemizer backend in one fixed order, and every method runs that order. A
TTS stack builds one frontend when it loads a voice, and calls it for each
text.

```python
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
from scriptconv.phonemizers import Phonemizer

frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.ESPEAK))
frontend.phonemize("Olá mundo. Tenho sede.")
# [['ɔ', 'l', 'ˈ', 'a', ' ', 'm', 'ˈ', 'u', '̃', 'ŋ', 'd', 'ʊ'], ['t', 'ˌ', 'e', 'ɲ', ...]]
```

The frontend needs the `phonemizers` extra, and the extra of its backend.

## The order of the stages

Every method reads the text first and cuts it into chunks after, in this
order:

1. Split out inline `[[phonemes]]` blocks. No stage reads the text inside a
   block, and its symbols go into the output as written.
2. Run the normalisation hook on the whole text, if the configuration sets
   one.
3. Apply casing, if the call sets a casing function.
4. Cut the normalised text into chunks: sentences by default.
5. For each chunk, lazily: diacritize, then run the backend. The backend cuts
   the chunk into clauses and writes the clause symbols.

A sentence split on raw text cuts at full stops that belong to the reading.
With `text2spoken` as the hook, `Prof. Smith arrived.` reads as `Professor
Smith arrived.`, but `Prof.` alone stays `Prof.`, so the split runs after the
hook. Step 5 stays lazy, so a long text starts to speak before its last
sentence is read.

A backend can own a stage. It then runs that stage itself, and the frontend
skips it. A backend can own `normalize`, `diacritize` or both. Tugaphone and
Arbtok own `diacritize`, and dizione owns `normalize`. The normalisation hook
runs for every backend that does not own `normalize`, because the caller
chooses it.

## Backends that read whole text

A backend that owns `normalize` reads the text with its own rules, so the
frontend cannot cut the text for it. Such a backend sets
`reads_whole_text = True` and gives `phonemize_segments(text, lang)`. It reads
the whole text once and reports one `Segment` per clause or sentence, in
reading order. A segment holds its phonemes, the clause symbol of the mark
that ends it, whether it ends a sentence, and the side streams of the backend,
such as stress, in step with the phonemes. The frontend groups the segments
into chunks, and writes the clause symbol of each segment by the rules of
[the clause tokens](phonemizers.md). dizione reads whole text.

A whole-text read has a size limit, `FrontendConfig.whole_text_limit`. Its
default is `WHOLE_TEXT_LIMIT`, and `None` turns it off. Above the limit, the
frontend first cuts the text at its paragraph breaks (one or more blank
lines), and never at a guessed sentence end. A paragraph break then ends a
sentence. The limit keeps one call of the slowest whole-text backend under
100 ms, from the timing of `scripts/time_owner_backends.py`.

An owner of `normalize` that cannot report its marks keeps
`reads_whole_text = False`. The frontend then cuts the text into sentences as
written, before casing, and the backend reads each sentence alone.

## Chunk size

`Stages(chunk=...)` sets what `phonemize_lazy` gives in one step:

| `Chunk` | A chunk is | Use |
| --- | --- | --- |
| `SENTENCE` (default) | One sentence | Live speech |
| `CLAUSE` | One clause | Faster first audio on long sentences |
| `PARAGRAPH` | The text between blank-line breaks | Fewer false sentence ends |
| `NONE` | The whole text | Offline rendering and dataset work |

The stage order is the same at every size. Two chunks join by the rule of the
clause tokens at every size: a chunk that ends in a clause symbol joins the
next one with no space, and any other chunk takes one space. So the size moves
only the cuts. At `NONE` size, the one chunk is the sentences joined by that
rule, and it is the result of `phonemize_flat`:

```python
frontend = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=True))
frontend.phonemize("Um, dois. Três.")                          # [['u', 'm', ',', ' ', 'd', 'o', 'i', 's', '.'], ['t', 'r', 'ê', 's', '.']]
frontend.phonemize("Um, dois. Três.", Stages(chunk=Chunk.CLAUSE))   # ['um, '], ['dois.'], ['três.']
frontend.phonemize("Um, dois. Três.", Stages(chunk=Chunk.NONE))     # ['um, dois.três.']
```

A backend can still cut inside a chunk that is too long for its own limit.

## Configuration

`FrontendConfig` holds what does not change from call to call:

| Field | Default | Meaning |
| --- | --- | --- |
| `lang` | Required | The language of the voice |
| `phonemizer` | `None` | The backend. `None` takes the default backend for `lang` |
| `alphabet` | `Alphabet.IPA` | The output alphabet of the backend |
| `model` | `None` | The model of a model-backed backend |
| `stages` | `Stages()` | The stage settings of the frontend |
| `normalizer` | `None` | A `(text, lang) -> str` hook. `None` means no normalisation |
| `keep_punctuation` | `False` | Keep clause punctuation, as the voice was trained |
| `strict` | `False` | Raise on a failure, instead of a warning |
| `whole_text_limit` | `WHOLE_TEXT_LIMIT` | Above this many characters, a whole-text backend reads each paragraph alone. `None` turns the cut off |

`TextFrontend(config, backend=None)` builds the backend from the
configuration. Give `backend=` an instance to use that instance. The backend
reads with the `keep_punctuation` of the configuration. When the instance has
another value, the frontend uses a shallow copy with the configured value, and
the instance that you gave does not change.

When the backend has a `get_lang` method, the frontend calls it once, so an
unsupported language fails when the frontend is built. The Grapheme and
Unicode backends take any language, and they have no `get_lang`.

## Stages for one call

`Stages` holds the stage settings. The configuration holds the settings of the
frontend, and each call can give its own:

| Field | Default | Meaning |
| --- | --- | --- |
| `normalize` | `None` | `False` skips the normalisation hook. `None` runs it, unless the frontend sets `False` |
| `diacritize` | `None` | `True` or `False` adds or skips the diacritizer |
| `diacritizer_model` | `None` | The model of the diacritizer |
| `lang` | `None` | The language of the text, for example a cloning reference |
| `casing` | `None` | A `str -> str` function. Training sets one |
| `chunk` | `None` | The chunk size. `None` takes `Chunk.SENTENCE` |

A value that the call sets wins. A value of `None` takes the value of the
frontend, and then the language of the configuration.

When neither sets `diacritize`, Arabic diacritizes and other languages do not.
Arabic means `ar` with any region, and each Arabic language in Arabic script,
such as `arz` and `apc`. linguatag measures these at a distance of 5 or less
from `ar`.

```python
frontend.phonemize("Tenho sede.", Stages(diacritize=True))   # bifonia marks 'sêde'
frontend.phonemize("hello", Stages(lang="en-GB", diacritize=False))
```

`diacritize=False` means that the frontend adds no diacritizer. A backend that
owns the stage still runs it, because it needs the marks to read the text.

## Methods

| Method | Returns | Use |
| --- | --- | --- |
| `phonemize_lazy(text, stages=None)` | An iterator of phoneme lists, one per chunk | Synthesis. The first chunk is ready before the next one is read |
| `phonemize(text, stages=None)` | A list of phoneme lists, one per chunk | The same, all at once |
| `phonemize_flat(text, stages=None)` | One phoneme list | Training. The same steps, and the backend's `phonemize_to_list` joins the sentences |
| `prepare(text, stages=None)` | The text after the stages | An engine that reads text and not phonemes. The whitespace at the edges of each piece of text between blocks stays |
| `identity()` | A `PhonemizerIdentity` | What phonemizes the language of the frontend, with `frontend` set to `FRONTEND_VERSION` |
| `with_backend(backend)` | A new `TextFrontend` | The same configuration with another backend instance |
| `register(graph)` | `None` | Adds a `text -> <alphabet>` edge to a `ConversionGraph` |

A chunk that gives no phonemes is not in the output. At `SENTENCE` and
`CLAUSE` size, a block adds its symbols to the chunk before it, and the text
after a block starts a new chunk. A space next to a block in the text becomes
a space symbol:

```python
frontend = TextFrontend(FrontendConfig("en", Phonemizer.UNICODE))
frontend.phonemize("ab [[xy]] cd")
# [['a', 'b', ' ', 'x', 'y', ' '], ['c', 'd']]
```

The edge that `register` adds gives the result of `phonemize_lazy`, not a
string, so it ends a route. A `stages=` key in the routing context goes to the
call:

```python
from scriptconv.graph import ConversionGraph

graph = ConversionGraph()
frontend.register(graph)
list(graph.convert("ab. cd.", "text", "ipa", stages=Stages(normalize=False)))
# [['a', 'b'], ['c', 'd']]
```

## Normalisation

scriptconv does not normalise text. It reads its input as normalised text. The
hook is off by default, and the caller sets it. `spoken_normalizer()` returns
`text2spoken.normalize` for the hook. It needs the `normalize` extra:

```python
from scriptconv.frontend import spoken_normalizer

frontend = TextFrontend(FrontendConfig("en", Phonemizer.UNICODE,
                                       normalizer=spoken_normalizer()))
frontend.phonemize("I have 5 cats.")
# [['I', ' ', 'h', 'a', 'v', 'e', ' ', 'f', 'i', 'v', 'e', ' ', 'c', 'a', 't', 's']]
```

A backend that always normalises names `normalize` in `owned_stages`, and the
frontend skips the hook for it. Every other backend reads what the hook gives.

## Failures

| Case | `strict=False` | `strict=True` |
| --- | --- | --- |
| A stage raises | A warning. The text continues without that stage | `StageError`, with the stage error as its cause |
| A diacritizer extra is missing | A warning at each call. The text continues without diacritics | `ImportError` when the frontend is built. The message names the extra |
| A sentence with letters or digits gives no phonemes | A warning | `UnreadTextError`. Its `unread` attribute holds the sentence |
| The backend does not support the language | `UnsupportedLanguageError` when the frontend is built | The same |

The warnings go to the `scriptconv.frontend` logger. A base install has no
diacritizer, and Arabic diacritizes by default, so an Arabic frontend without
the `tashkeel` extra warns and reads the text without diacritics.

## The module function

`scriptconv.phonemizers.phonemize(text, lang)` does not use `TextFrontend`. The
backend reads the whole text with `phonemize_string` and returns one string. No
stage runs, the text is not split into sentences, and an inline block reaches
the backend as text.

The result can differ from the phonemes of a frontend for the same text: the
frontend splits sentences and blocks, and it can diacritize and normalise.
Build a `TextFrontend` to get the phonemes that a voice reads.

`identity()` of a frontend carries `FRONTEND_VERSION`, the version of the
stage order. A change to the steps raises it, so a dataset phonemized under
older steps is detectable. A backend called directly has `frontend=None`.

---
[← phonemizers](phonemizers.md) · [Home](../README.md) · [ovos →](ovos.md)
