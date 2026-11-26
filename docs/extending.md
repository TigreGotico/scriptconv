# Add a backend

<!-- agent-hint
covers: how to run your own phonemizer inside TextFrontend, and the steps to add a backend to the registry
source: BasePhonemizer in scriptconv/phonemizers/base.py, scriptconv/phonemizers/enums.py and registry.py, scripts/backend_table.py, tests/test_phonemizers_base.py
generated: no
verify: python scripts/check_doc_page.py docs/extending.md
see: docs/phonemizers.md, docs/backends.md, docs/frontend.md
-->

This page shows how to use a phonemizer of your own with `TextFrontend`, and
how to add a backend to the registry so that a voice configuration can name
it.

## Run your own backend

A backend is a subclass of `BasePhonemizer` with one method,
`phonemize_string(text, lang)`. It returns the phonemes of one sentence as a
string. This backend keeps the vowels:

```pycon
>>> from scriptconv.phonemizers import Alphabet, BasePhonemizer
>>> class Vowels(BasePhonemizer):
...     def phonemize_string(self, text, lang):
...         return "".join(char for char in text.lower() if char in "aeiou ")
...
>>> backend = Vowels(Alphabet.UNICODE)
>>> backend.phonemize_to_list("Hello", "en")
['e', 'o']
>>> backend.phonemize("Hello. Bye", "en")
[['e', 'o'], ['e']]

```

The base class cuts the text into sentences and calls `phonemize_string` on
each one. Hand the instance to a `TextFrontend` to get the stage order, the
chunk sizes and inline phoneme blocks:

```pycon
>>> from scriptconv.frontend import FrontendConfig, TextFrontend
>>> frontend = TextFrontend(FrontendConfig("en", alphabet=Alphabet.UNICODE), backend=backend)
>>> frontend.phonemize("Hello world. Good day.")
[['e', 'o', ' ', 'o'], ['o', 'o', ' ', 'a']]
>>> "".join(frontend.phonemize_flat("Hello world. Good day."))
'eo o oo a'

```

The frontend asks a backend that has a `get_lang` method whether it supports
the language, and a backend without one takes any language.
[phonemizers.md](phonemizers.md#the-contract) lists the rest of the contract:
`owned_stages`, `reads_whole_text`, `engine_distribution` and the revision.

## Add the backend to the registry

A backend in the registry has a name that a voice configuration stores. These
steps add one to scriptconv:

1. Add a member to `Phonemizer` in `scriptconv/phonemizers/enums.py`. The
   value is wire format, so choose it once.
2. Add the row `(module, class name, extra)` to `PHONEMIZER_REGISTRY` in
   `scriptconv/phonemizers/registry.py`. The class imports on first use, so
   the module may import the engine at the top.
3. Add the extra to `pyproject.toml`, and a row for it to the Extras table of
   the README. An extra groups backends by purpose, so a backend that fits an
   existing extra joins it.
4. Put the wrapper in scriptconv-copyleft or scriptconv-nonfree when the
   engine is under a copyleft or a non-commercial licence, and give the
   registry row the module path in that package.
5. Run `python scripts/backend_table.py --write` to add the row to
   [backends.md](backends.md#the-table).
6. Update the member count in `tests/test_phonemizers_base.py`, and add tests
   for the wrapper.

Run the suite and the checks of `AGENTS.md` before you push. The registry then
resolves the name of your backend:

```pycon
>>> from scriptconv.phonemizers import Phonemizer, get_phonemizer_class
>>> get_phonemizer_class(Phonemizer.UNICODE).__name__
'UnicodeCodepointPhonemizer'

```

---
[← Prev](performance.md) · [Home](index.md) · [Next →](reference.md)
