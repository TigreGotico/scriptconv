# Reference: the public names

<!-- agent-hint
covers: the signature, the behaviour and an example of each public name that voice code imports, and the page that explains every other name in __all__
source: `__all__` in scriptconv/__init__.py, scriptconv/phonemizers/__init__.py and scriptconv/frontend.py; scriptconv/diacritics.py, scriptconv/graph.py, scriptconv/scripts.py
generated: no
verify: python scripts/check_doc_page.py docs/reference.md
see: docs/frontend.md, docs/phonemizers.md, docs/graph.md, docs/stack.md
-->

This page gives the exact signature and one example for each name that a
voice engine imports from scriptconv, and lists every other public name with
the page that explains it. The signature blocks are checked against the code.

The examples use the `graphemes` backend, which needs only the `phonemizers`
extra, and the `normalize` and `pt` extras where a line says so.

```bash
uv pip install --prerelease=allow "scriptconv[normalize,pt]"
```

## scriptconv.frontend

`TextFrontend` takes text to phonemes through one stage order. The page
[frontend.md](frontend.md) describes each option, and [stack.md](stack.md)
shows the order of the stages.

```python
from scriptconv.frontend import (FRONTEND_VERSION, WHOLE_TEXT_LIMIT, Chunk, FrontendConfig, Stages,
                                 TextFrontend, spoken_normalizer)
from scriptconv.phonemizers import Alphabet, Phonemizer
```

| Method | Returns | What it does |
|---|---|---|
| `prepare(text, stages=None)` | `str` | The text after the normalise, casing and diacritize stages, for an engine that reads text, not phonemes |
| `phonemize(text, stages=None)` | `list[list[str]]` | One list of phonemes for each chunk |
| `phonemize_lazy(text, stages=None)` | iterator of `list[str]` | The same chunks, each read when the caller asks for it |
| `phonemize_flat(text, stages=None)` | `list[str]` | All the phonemes as one list, for training: the `none` chunk |
| `segments(text, stages=None)` | iterator of `Segment` | The chunks with the side streams of the backend |
| `say_as(text, interpret_as, format=None, detail=None, lang=None)` | `str` | The text in the form that an SSML `say-as` names |
| `identity()` | `PhonemizerIdentity` | What phonemizes this frontend's language |
| `with_backend(backend)` | `TextFrontend` | A frontend with the same configuration and another backend |
| `register(graph)` | `None` | Add a `text` to alphabet edge to a conversion graph |

```pycon
>>> from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
>>> from scriptconv.phonemizers import Alphabet, Phonemizer
>>> frontend = TextFrontend(FrontendConfig("en", Phonemizer.GRAPHEMES, Alphabet.GRAPHEMES))
>>> frontend.prepare("Hi there. Bye!")
'Hi there. Bye!'
>>> frontend.phonemize("Hi there. Bye!")
[['h', 'i', ' ', 't', 'h', 'e', 'r', 'e'], ['b', 'y', 'e']]
>>> frontend.phonemize_flat("Hi there. Bye!")
['h', 'i', ' ', 't', 'h', 'e', 'r', 'e', ' ', 'b', 'y', 'e']
>>> frontend.phonemize("Hi there. Bye!", Stages(chunk="none"))
[['h', 'i', ' ', 't', 'h', 'e', 'r', 'e', ' ', 'b', 'y', 'e']]

```

`prepare` leaves a text that has no normaliser as it is. `phonemize` cuts at
sentences, and `phonemize_flat` joins the sentences into one list, with a space
between two sentences where the text writes whitespace. The constructor raises
`UnsupportedLanguageError` when the backend does not support the language.
In strict mode it raises `ImportError` when a diacritizer that the language
needs is missing.

`Stages` holds the stage settings of one call, and `FrontendConfig` holds
what a frontend is built from. A value of `None` in `Stages` takes the value
of the frontend.

```python
@dataclass(frozen=True)
class Stages:
    normalize: Optional[bool] = None
    diacritize: Optional[bool] = None
    diacritizer_model: Optional[str] = None
    lang: Optional[str] = None
    casing: Optional[Callable[[str], str]] = None
    chunk: Optional[Chunk] = None
```

```python
@dataclass(frozen=True)
class FrontendConfig:
    lang: str
    phonemizer: Optional[Phonemizer] = None
    alphabet: Alphabet = Alphabet.IPA
    model: Optional[str] = None
    stages: Stages = Stages()
    normalizer: Optional[Callable[[str, str], str]] = None
    phonemizer_lang: Optional[str] = None
    keep_punctuation: bool = False
    strict: bool = False
    whole_text_limit: Optional[int] = 1750
```

`Stages.chunk` takes a `Chunk` or its value. Another value raises
`ValueError`.

```pycon
>>> from scriptconv.frontend import Chunk
>>> [chunk.value for chunk in Chunk]
['sentence', 'clause', 'paragraph', 'none']
>>> Stages(chunk="clause").chunk.value
'clause'
>>> Stages(chunk="word")
Traceback (most recent call last):
    ...
ValueError: ...chunk 'word' is not one of 'sentence', 'clause', 'paragraph', 'none'...

```

`spoken_normalizer()` returns `text2spoken.normalize`, the hook for
`FrontendConfig.normalizer`. It raises `ImportError` when the `normalize` extra
is missing.

```python
def spoken_normalizer()
```

```pycon
>>> from scriptconv.frontend import spoken_normalizer
>>> spoken_normalizer()("Tenho 25 anos.", "pt-PT")
'Tenho vinte e cinco anos.'

```

The module also exports `FRONTEND_VERSION`, the version of the stage order
that `identity()` records, and `WHOLE_TEXT_LIMIT`, the default of
`FrontendConfig.whole_text_limit`. See [performance.md](performance.md).

```pycon
>>> from scriptconv.frontend import FRONTEND_VERSION, WHOLE_TEXT_LIMIT
>>> (FRONTEND_VERSION, WHOLE_TEXT_LIMIT)
(2, 1750)

```

## scriptconv.phonemizers

The registry builds a backend from a `Phonemizer` member. The page
[phonemizers.md](phonemizers.md) holds the contract and the per-language
defaults.

```python
from scriptconv.phonemizers import (Alphabet, BasePhonemizer, LANG_DEFAULTS, MissingLanguageError,
                                    PHONEMIZER_REGISTRY, Phonemizer, PhonemizerIdentity,
                                    UnicodeCodepointPhonemizer, UnsupportedLanguageError,
                                    get_phonemizer, get_phonemizer_class, phonemize,
                                    phonemizer_for_lang)
```

```python
def get_phonemizer(phonemizer, alphabet=Alphabet.IPA, model=None, **kwargs)
```

`get_phonemizer` builds an instance of the backend. It passes `alphabet` and
`model` to the constructor parameters of those names, and sets `normalizer=`
and `keep_punctuation=` on the instance. It raises `ValueError` when you give
a non-empty `model` to a backend that has no model parameter.

```python
def get_phonemizer_class(phonemizer)
```

`get_phonemizer_class`, also at `scriptconv.phonemizers.registry`, returns the
class and builds nothing. It accepts a `Phonemizer` member or its value. It
raises `ImportError` that names the extra when the engine package is missing.

```python
def phonemizer_for_lang(lang, alphabet=Alphabet.IPA, override=None, model=None, **kwargs)
```

`phonemizer_for_lang` builds the default backend for a language. The first of
these wins: `override`, the `LANG_DEFAULTS` candidates that write the alphabet,
orthography2ipa for IPA, and espeak.

```python
def phonemize(text, lang, alphabet=Alphabet.IPA, override=None, model=None, **kwargs)
```

`phonemize` builds a backend and returns the phoneme string of one text. Keep
the backend of `phonemizer_for_lang` to read many texts.

```pycon
>>> from scriptconv.phonemizers import Alphabet, LANG_DEFAULTS, PHONEMIZER_REGISTRY, Phonemizer, get_phonemizer, get_phonemizer_class
>>> get_phonemizer_class("graphemes").__name__
'GraphemePhonemizer'
>>> get_phonemizer(Phonemizer.GRAPHEMES, Alphabet.GRAPHEMES).phonemize_string("Olá, Mundo!", "pt")
'olá, mundo!'
>>> PHONEMIZER_REGISTRY[Phonemizer.UNICODE]
('scriptconv.phonemizers.base', 'UnicodeCodepointPhonemizer', None)
>>> len(PHONEMIZER_REGISTRY) == len(Phonemizer)
True
>>> sorted(LANG_DEFAULTS)
['ar', 'eu', 'gl', 'he', 'lir', 'mwl', 'pt', 'ru']

```

`PHONEMIZER_REGISTRY` maps each `Phonemizer` member to a tuple of module, class
name and extra. The extra is `None` for a backend with no engine. `LANG_DEFAULTS`
maps a primary language subtag to its candidate backends in order.

`register(graph)` adds the `text` to `ipa` edges to a conversion graph. See
[graph.md](graph.md).

### Enums

`Phonemizer` names the backend, and `Alphabet` names the symbol set that it
writes. Both are `str` enums, and their values are wire format: voice
configuration files store them, so a value never changes.
[backends.md](backends.md) lists the members of `Phonemizer`. `Alphabet`
has these members:

```pycon
>>> [alphabet.value for alphabet in Alphabet][:8]
['unicode', 'ipa', 'arpa', 'sampa', 'x-sampa', 'rfe', 'hangul', 'kana']
>>> len(Alphabet)
24

```

### BasePhonemizer and its subclasses

`BasePhonemizer` is the abstract base of every backend. A subclass gives
`phonemize_string(text, lang)`, and the base class gives the rest. See
[extending.md](extending.md) for a worked subclass.

| Member | What it is |
|---|---|
| `phonemize_string(text, lang)` | Abstract. The phonemes of one sentence as a string |
| `phonemize_to_list(text, lang)` | All the phonemes as one flat list |
| `phonemize(text, lang)` | One list for each sentence |
| `phonemize_lazy(text, lang)` | The same lists, each read when asked for |
| `phonemize_segments(text, lang)` | `Segment` values; a whole-text backend overrides it |
| `identity(lang)` | The `PhonemizerIdentity` of the backend for the language |
| `match_lang(target, valid_langs)` | The closest supported language, or an error |
| `keep_punctuation`, `strict` | Flags that the frontend sets on the instance |
| `owned_stages`, `reads_whole_text`, `engine_distribution` | Class attributes that tell the frontend what the backend runs itself |

`match_lang` raises `MissingLanguageError` when the target is `None`, `""` or
`"und"`, and `UnsupportedLanguageError` when no supported language is close.

```pycon
>>> from scriptconv.phonemizers import BasePhonemizer
>>> BasePhonemizer.match_lang("pt-BR", ["pt-PT", "en-US"])
'pt-PT'
>>> BasePhonemizer.match_lang("und", ["en"])
Traceback (most recent call last):
    ...
scriptconv.phonemizers.base.MissingLanguageError: ...no language provided to phonemize: 'und'...
>>> BasePhonemizer.match_lang("zh", ["en"])
Traceback (most recent call last):
    ...
scriptconv.phonemizers.base.UnsupportedLanguageError: ...unsupported language code: zh...

```

`UnicodeCodepointPhonemizer(form="NFD")` returns the codepoints of the text in a
Unicode normal form. `GraphemePhonemizer` returns the text itself after its
character rules. Neither needs an engine, and each accepts any language.

```pycon
>>> from scriptconv.phonemizers import UnicodeCodepointPhonemizer
>>> UnicodeCodepointPhonemizer().phonemize_to_list("é", "und")
['e', '́']
>>> UnicodeCodepointPhonemizer("NFC").phonemize_to_list("é", "und")
['é']

```

### PhonemizerIdentity and Segment

`PhonemizerIdentity` records what produced a phoneme sequence. A voice stores
it and compares it later. `differs_from(other)` names the fields that differ,
`revision` first.

```python
@dataclass(frozen=True)
class PhonemizerIdentity:
    backend: str
    distribution: str
    version: str
    lang: str
    revision: Optional[str] = None
    frontend: Optional[int] = None
```

`frontend` is `None` for a backend called directly, and it tells which
revision `revision` holds. Compare an identity from `backend.identity(lang)`
with another from a backend, and one from `TextFrontend.identity()` with
another from a frontend.

```pycon
>>> from scriptconv.phonemizers import PhonemizerIdentity
>>> first = PhonemizerIdentity("tugaphone", "tugaphone", "1.0", "pt-PT", revision="a")
>>> second = PhonemizerIdentity("tugaphone", "tugaphone", "1.1", "pt-PT", revision="b")
>>> first.differs_from(second)
('revision', 'version')

```

`Segment` is one sentence or clause that a backend reads whole, with its
side streams. `TextFrontend.segments` and `BasePhonemizer.phonemize_segments`
yield it.

| Field | Default | Meaning |
|---|---|---|
| `phonemes` | Required | The output symbols, a tuple |
| `mark` | `None` | The clause symbol that ends the segment |
| `ends_sentence` | `True` | Whether the segment ends a sentence |
| `streams` | `{}` | Side streams such as stress, each in step with `phonemes` |
| `ends_paragraph` | `False` | Whether a blank line follows the segment |
| `bounded` | `False` | Whether `phonemes` starts and ends with the backend's start and end symbols |
| `text` | `None` | The text that the backend read for the segment |

### Chunk types and errors

`PhonemizedChunks` is `list[list[str]]`, the type that `phonemize` returns:
one list of phonemes for each sentence. `TextChunks` is a list of
`(substring, terminator, ends_sentence)` tuples, the type that
`BasePhonemizer.chunk_text` returns. `RawPhonemizedChunks` has the same
shape with phonemes in place of the substring.

All the errors below subclass `FrontendError`, which subclasses `ValueError`,
except `MissingLanguageError`, which subclasses `ValueError` directly.

| Error | Raised when |
|---|---|
| `UnsupportedLanguageError` | The backend has no support for the language |
| `MissingLanguageError` | No language reached `match_lang`: the target was `None`, `""` or `"und"` |
| `StageError` | A text stage failed in strict mode |
| `UnreadTextError` | Text with letters or digits gave no phonemes in strict mode. `unread` holds the pieces |
| `ModelUnavailableError` | A model is not cached and cannot be fetched offline |

## scriptconv.diacritics

`diacritize` adds the marks that tell a phonemizer how to read a text:
Arabic tashkeel, Hebrew niqqud, word stress, and European-Portuguese
homograph marks. A language that needs none comes back unchanged. The
sections of [phonemizers.md](phonemizers.md#diacritics-before-g2p-diacritize)
list the backend of each language.

```python
from scriptconv.diacritics import DIACRITIZED, diacritize, strip_diacritics
```

```python
def diacritize(text, lang="und", diacritizer_model=None, waqf=None, **kwargs)
```

```python
def strip_diacritics(text, lang="und", **_)
```

`strip_diacritics` removes the overlay marks that `diacritize` adds, and it
raises `ValueError` for a language whose marks are native spelling.

```pycon
>>> from scriptconv.diacritics import DIACRITIZED, diacritize, strip_diacritics
>>> diacritize("Tenho muita sede hoje.", "pt-PT")
'Tenho muita sêde hoje.'
>>> diacritize("Tenho muita sede hoje.", "en")
'Tenho muita sede hoje.'
>>> strip_diacritics("за́мок", "ru")
'замок'
>>> DIACRITIZED
'text-diacritized'

```

`DIACRITIZED` is the name of the graph node that `diacritics.register` adds.
The `STRESS_LANGS` set holds the languages whose stress `diacritize` restores.

## scriptconv.graph

`ConversionGraph` routes a conversion between representations. An `Edge` is
one converter, and `DEFAULT_GRAPH` holds the edges of scriptconv. The page
[graph.md](graph.md) draws the graph and shows the routing.

```python
from scriptconv import DEFAULT_GRAPH, REPRESENTATIONS, ConversionGraph, Edge
```

```python
@dataclass(frozen=True)
class Edge:
    src: str
    dst: str
    fn: Callable[..., str]
    lossless: bool = False
    requires: Optional[str] = None
    cost: float = -1.0
```

`cost` defaults to 1 for a lossless edge and 10 for a lossy one, and routing
takes the cheapest path.

| `ConversionGraph` member | What it does |
|---|---|
| `ConversionGraph(edges=None)` | A graph of the given edges |
| `route(src, dst)` | The cheapest list of edges; `ValueError` when none exists |
| `convert(text, src, dst, **context)` | Converts along the route, and passes the context to each edge |
| `can_convert(src, dst)` | Whether a route exists |
| `register(edge)` | Adds an edge |
| `extend(register_fn)` | A copy with the edges that the function adds |
| `copy()` | An independent copy |
| `nodes`, `edges` | The representation ids, and the edges |

```pycon
>>> from scriptconv import ConversionGraph, DEFAULT_GRAPH, Edge, REPRESENTATIONS
>>> [f"{e.src}->{e.dst}" for e in DEFAULT_GRAPH.route("arpa", "x-sampa")]
['arpa->ipa', 'ipa->x-sampa']
>>> (len(DEFAULT_GRAPH.nodes), len(DEFAULT_GRAPH.edges), len(REPRESENTATIONS))
(20, 24, 20)
>>> graph = ConversionGraph([Edge("a", "b", lambda text, **_: text.upper(), lossless=True)])
>>> graph.convert("abc", "a", "b")
'ABC'

```

## scriptconv.scripts

```python
from scriptconv import normalize_script_tag
```

```python
def normalize_script_tag(label)
```

`normalize_script_tag` maps a free-form script label to its ISO 15924 code, or
`None`. It accepts English names, labels such as `syllabics`, and codes in any
case.

```pycon
>>> from scriptconv import normalize_script_tag
>>> normalize_script_tag("latin")
'Latn'
>>> normalize_script_tag("Cyrillic")
'Cyrl'
>>> normalize_script_tag("latn")
'Latn'
>>> normalize_script_tag("syllabics")
'Cans'
>>> print(normalize_script_tag("klingon"))
None

```

## Every other public name

| Names | Page |
|---|---|
| `Script`, `SCRIPT_REGISTRY`, `char_script`, `detect_script`, `script_distribution`, `script_runs`, `base_direction`, `lang_to_script`, `script_to_langs` | [scripts.md](scripts.md) |
| `Notation`, `UnknownSymbolError`, `NotationInfo`, `NOTATION_INFO`, `convert`, `can_convert`, `convert_batch`, `looks_like_ipa` and the `*_to_ipa` and `ipa_to_*` functions | [notation.md](notation.md) |
| `decompose_hangul`, `hira_to_kana`, `kana_to_hira` | [translit.md](translit.md) |
| `cangjie_code`, `to_cangjie`, `to_pinyin`, `to_bopomofo` | [translit.md](translit.md) and [readings.md](readings.md) |
| `Convention`, `Transition`, `CONVENTION_REGISTRY`, `conventions_for`, `restyle`, `strip`, `apply`, `detect_convention` | [conventions.md](conventions.md) |
| `Representation`, `REPRESENTATIONS` | [graph.md](graph.md) |

`CONVENTION_REGISTRY` maps a convention id to its `Convention`, and a
`Transition` is one rewrite between two styles of a convention.

```pycon
>>> from scriptconv import CONVENTION_REGISTRY
>>> sorted(CONVENTION_REGISTRY)[:3]
['jamo-form', 'kashida', 'niqqud']

```

---
[← Prev](extending.md) · [Home](index.md)
