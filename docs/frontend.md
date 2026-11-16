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
4. Cut the normalised text at its blank lines, then into sentences, or into
   clauses at `CLAUSE` size.
5. For each sentence or clause, lazily: diacritize, then run the backend. The
   backend cuts a sentence into clauses and writes the clause symbols.
6. Group the sentences into chunks of the size that the call sets, and join
   the sentences of a chunk by one rule.

A sentence split on raw text cuts at full stops that belong to the reading.
With `text2spoken` as the hook, `Prof. Smith arrived.` reads as `Professor
Smith arrived.`, but `Prof.` alone stays `Prof.`, so the split runs after the
hook. Step 5 stays lazy, so a long text starts to speak before its last
sentence is read.

Each stage, the hook, casing and the diacritizer, reads its text without the
whitespace at the edges, and the frontend puts that whitespace back around
the result. So a diacritizer that marks the last letter of `عندي ` before a
block marks the `ي`, not the space after it.

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
reading order. A segment holds:

- its phonemes,
- the clause symbol of the mark that ends it,
- whether it ends a sentence, and whether a paragraph break follows it,
- the side streams of the backend, such as stress, in step with the phonemes,
- whether its phonemes start and end with the backend's start and end
  symbols (`bounded`), as `<bos>` and `<eos>`.

The frontend groups the segments into chunks at every size, and writes the
clause symbol of each segment by the rules of
[the clause tokens](phonemizers.md). Where two bounded segments join, the
inner end and start symbols go, with their stream values. A bounded segment
holds its own marks, so the frontend writes no clause symbol into it, and the
segment's mark only tells that it ends in one. Where no mark ends the first
of two bounded segments, the backend's word break comes between them.
`TextFrontend.segments` gives each chunk as a `Segment`, with the streams in
step with its symbols. A word break that the frontend adds takes the values
of the backend's `word_break()`, and a clause symbol or a block's symbol
takes 0 in every stream. dizione reads whole text, and with
`DizionePhonemizer(tokens=True)` its segments are its own tokens, so a voice
gets the ids and the stress of each chunk:

```python
from scriptconv.phonemizers.dizione import DizionePhonemizer

frontend = TextFrontend(FrontendConfig("en-US"), DizionePhonemizer(tokens=True))
[(s.phonemes, s.streams["ids"]) for s in frontend.segments("Hi, Bob.", Stages(chunk="clause"))]
# [(('<bos>', 'h', 'aɪ', ',', '<eos>'), (1, 31, 60, 5, 2)), (('<bos>', 'b', 'ɑː', 'b', '.', '<eos>'), (1, 18, 53, 18, 6, 2))]
```

A whole-text read has a size limit, `FrontendConfig.whole_text_limit`. Its
default is `WHOLE_TEXT_LIMIT`, 2,000 characters, and `None` turns it off. Above the limit, the
frontend first cuts the text at its paragraph breaks (one or more blank
lines), and never at a guessed sentence end. A paragraph break then ends a
sentence. The limit keeps one call of the slowest whole-text backend under
100 ms, from the timing of `scripts/time_owner_backends.py` on prose and on a
text dense in dates and prices. Its output is in
`scripts/time_owner_backends.txt`.

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

`chunk` takes a `Chunk` or its value, such as `"clause"`. Any other value
raises `ValueError`.

The stage order is the same at every size: the frontend reads the whole text
first, then cuts it into sentences, and a chunk is a sentence, a clause, the
sentences of a paragraph, or every sentence. One rule joins two pieces at every
size, the rule of the clause tokens: a piece that ends in a clause symbol, or
in a space, joins the next one with no space, and any other piece takes one
space. Inside a sentence, a clause that ends in `!` or `?` takes a space after
the symbol, as the text writes one. No chunk starts with a space. So the
chunks of every size, joined by this rule, are the result of
`phonemize_flat`, and at `NONE` size the one chunk is that result:

```python
frontend = TextFrontend(FrontendConfig("pt", Phonemizer.GRAPHEMES, keep_punctuation=True))
text = "Olá! Tudo bem? Sim.\n\nAté logo."
frontend.phonemize(text)                                # 'olá! tudo bem?', 'sim.', 'até logo.'
frontend.phonemize(text, Stages(chunk="clause"))        # 'olá! ', 'tudo bem?', 'sim.', 'até logo.'
frontend.phonemize(text, Stages(chunk="paragraph"))     # 'olá! tudo bem?sim.', 'até logo.'
frontend.phonemize(text, Stages(chunk="none"))          # 'olá! tudo bem?sim.até logo.'
```

The comments show each chunk as a string. The frontend cuts the normalised
text at each blank line before it cuts sentences. So a blank line ends a
paragraph, and a sentence, whatever comes before it: a title with no mark, a
`!`, a `:`, a `;`, an ellipsis, or a closing quote or bracket. The hook reads
the whole text before the cut, so a mark that belongs to the reading reads as
in the whole text.

dizione reads whole text, and it reads a blank line as a space. It ends a
paragraph only at a `.`, `?` or `!` that a blank line follows. After a `:`, a
`;`, an ellipsis or a title, the paragraph runs on to the next blank line that
follows a sentence end. A full stop that belongs to the reading, as in `Call
Dr.\n\nSmith now.`, ends no paragraph.

At `CLAUSE` size, the backend reads each clause alone. A backend that reads a
word by the word after it, as orthography2ipa does at a word boundary, can
read the last word of a clause another way.

A backend that writes its own output, and so overrides `phonemize_lazy` or
`phonemize_to_list`, appends no clause symbol: its marks join as any other
symbol.

The frontend calls `phonemize_segments` on each sentence or clause of a
backend that does not read whole text. By default a segment is a sentence of
`phonemize_lazy`. Shami overrides it: each sentence is a bounded segment, with
its own `<bos>` and `<eos>` and a `language_ids` stream. So each chunk has one
`<bos>` and one `<eos>` at every size. Where the frontend joins two sentences,
the inner pair goes with its language ids, and a space with the language id
of a space comes between them, as Shami reads the two sentences in one call.

An inline block in a chunk of bounded segments goes inside the chunk's start
and end symbols. The backend writes the marks of such a chunk, so the
frontend reads no mark around the block. Its word break, such as dizione's
`<sp>` in token mode, comes before the block where the text has whitespace
and the chunk does not end in a mark, and after the block where the text has
a space. A word break never comes right before the end symbol: the text after
a block starts a new sentence, so a sentence chunk that ends in a block ends
in the block's symbols. A text that holds only blocks gives no start and end symbols,
because the backend reads no text.

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
| `chunk` | `None` | The chunk size, a `Chunk` or its value. `None` takes `Chunk.SENTENCE` |

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
| `phonemize_flat(text, stages=None)` | One phoneme list | Training. The sentence chunks of `phonemize`, joined by the rule of the clause tokens |
| `segments(text, stages=None)` | An iterator of `Segment`, one per chunk | The chunks with the side streams of a whole-text backend, in step with the symbols |
| `prepare(text, stages=None)` | The text after the stages | An engine that reads text and not phonemes. The whitespace at the edges of each piece of text between blocks stays |
| `identity()` | A `PhonemizerIdentity` | What phonemizes the language of the frontend, with `frontend` set to `FRONTEND_VERSION` |
| `with_backend(backend)` | A new `TextFrontend` | The same configuration with another backend instance |
| `register(graph)` | `None` | Adds a `text -> <alphabet>` edge to a `ConversionGraph` |

A chunk that gives no phonemes is not in the output. A block adds its symbols
to the sentence before it, and the text after a block starts a new sentence. A
space next to a block in the text becomes a space symbol:

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
