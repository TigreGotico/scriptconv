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

Every method runs the same steps in the same order:

1. Split out inline `[[phonemes]]` blocks. No stage reads the text inside a
   block, and its symbols go into the output as written.
2. Split the text into sentences. `prepare` and `phonemize_flat` do not split
   the text.
3. Run the normalisation hook, if the configuration sets one.
4. Apply casing, if the call sets a casing function.
5. Diacritize.
6. Run the backend.

A backend can own a stage. It then runs that stage itself, and the frontend
skips it. `diacritize` is the only stage a backend can own, and Tugaphone and
Arbtok own it. The normalisation hook runs for every backend, because the
caller chooses it.

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
| `phonemize_lazy(text, stages=None)` | An iterator of phoneme lists, one per sentence | Synthesis. The first sentence is ready before the next one is read |
| `phonemize(text, stages=None)` | A list of phoneme lists, one per sentence | The same, all at once |
| `phonemize_flat(text, stages=None)` | One phoneme list | Training. The text is not split into sentences, and the backend's `phonemize_to_list` reads it |
| `prepare(text, stages=Stages(normalize=False))` | The text after the stages | An engine that reads text and not phonemes |
| `identity()` | A `PhonemizerIdentity` | What phonemizes the language of the frontend |
| `with_backend(backend)` | A new `TextFrontend` | The same configuration with another backend instance |
| `register(graph)` | `None` | Adds a `text -> <alphabet>` edge to a `ConversionGraph` |

A sentence that gives no phonemes is not in the output. A block adds its
symbols to the sentence before it, and the text after a block starts a new
sentence. A space next to a block in the text becomes a space symbol:

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

A backend that needs its own normalisation runs it. The hook runs before that
backend, and the backend reads what the hook gives.

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
Training uses `phonemize_flat`, which does not split sentences, so its result
can also differ from `phonemize`. Build a `TextFrontend` to get the phonemes
that a voice reads.

---
[← phonemizers](phonemizers.md) · [Home](../README.md) · [ovos →](ovos.md)
