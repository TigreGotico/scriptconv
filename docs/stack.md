# scriptconv in the speech stack

<!-- agent-hint
covers: the stage order of TextFrontend and the library that runs each stage
source: scriptconv/frontend.py (module docstring, `TextFrontend._text_pieces`), `diacritize` in scriptconv/diacritics.py
generated: no
verify: python -c '(I:=__import__,ast:=I("ast"),re:=I("re"),sys:=I("sys"),inspect:=I("inspect"),enum:=I("enum"),dataclasses:=I("dataclasses"),unittest:=I("unittest"),f:=sys.argv[1],g:={},T:=unittest.TestCase(),B:=re.findall(r"\x60{3}python\n(.*?)\x60{3}",open(f,encoding="utf-8").read(),re.S),K:=lambda o:[(p.name,p.kind,p.default) for p in inspect.signature(o).parameters.values()] if not isinstance(o,type) else [(m.name,m.value) for m in o] if issubclass(o,enum.Enum) else [x.name for x in dataclasses.fields(o)],D:=lambda b:((s:=re.sub(r"\)( -> .+)?$",r")\1: ...",b.strip()) if b.startswith("def") else b),(h:=dict(g)),exec("from __future__ import annotations\nfrom enum import Enum\nfrom dataclasses import dataclass\n"+s,h),[K(h[d.name])==K(g[d.name]) or (d.name,K(h[d.name]),K(g[d.name])) for d in ast.parse(s).body])[-1],C:=lambda s,L:None if not isinstance(s,ast.Expr) else (m.group(1) if (m:=re.search(r"\s#\s?(.*)$",L[s.end_lineno-1])) else L[s.end_lineno][2:] if s.end_lineno<len(L) and L[s.end_lineno].startswith("# ") else None),X:=lambda s:compile(ast.Expression(s.value),f,"eval"),Q:=lambda s,e:(T.assertRaisesRegex(eval(e.split(":")[0],g),re.escape(e.partition(":")[2].strip()),eval,X(s),g) or True) if re.match(r"\w+Error\b",e) else (True if (v:=eval(X(s),g))==ast.literal_eval(e) else (ast.unparse(s),e,v)),R:=lambda s,L:exec(compile(ast.Module([s],[]),f,"exec"),g) if (c:=C(s,L)) is None else Q(s,c.split("  ")[0].strip()),r:=[y for b in B for y in (D(b) if re.match(r"def |class |@",b) else [R(s,b.splitlines()) for s in ast.parse(b).body]) if y is not None],w:=[y for y in r if y is not True],print("OK",len(r)) if not w else sys.exit("MISMATCH "+repr(w)))' docs/stack.md
see: docs/frontend.md, docs/backends.md
-->

scriptconv is the one stop for text conversion in the TigreGotico speech
stack. A voice in [phoonnx](https://github.com/TigreGotico/phoonnx) builds a
`TextFrontend` from scriptconv and gives it text. The frontend calls the stage
libraries and one phonemizer backend, each through an optional extra.

## A walk-through

Install the normaliser and an espeak backend:

```bash
uv pip install --prerelease=allow "scriptconv[normalize,espeak]"
```

Build a frontend with `text2spoken` as its normalisation hook, and look at the
text after the stages:

```python
from scriptconv.frontend import FrontendConfig, Stages, TextFrontend, spoken_normalizer
from scriptconv.phonemizers import Phonemizer

frontend = TextFrontend(FrontendConfig("pt-PT", Phonemizer.ESPEAK, normalizer=spoken_normalizer()))
frontend.prepare("O Prof. Silva tem 25 anos.")
# 'O Professor Silva tem vinte e cinco anos.'
```

Without the hook, the same call returns the text as written:

```python
plain = TextFrontend(FrontendConfig("pt-PT", Phonemizer.ESPEAK))
plain.prepare("O Prof. Silva tem 25 anos.")
# 'O Prof. Silva tem 25 anos.'
```

`frontend.phonemize(text)` runs the same stages, then the backend, and returns
one list of phonemes per sentence. The raw text splits after `Prof.`, and the
normalised text does not:

```python
len(frontend.phonemize("O Prof. Silva tem 25 anos."))   # 1
len(plain.phonemize("O Prof. Silva tem 25 anos."))      # 2
```

## The order of the stages

Every method of `TextFrontend` runs one order:

1. Split out inline `[[phonemes]]` blocks. No stage reads a block.
2. Run the normalisation hook on the whole text, if the caller set one.
3. Apply casing, if the call sets a casing function.
4. Cut the text into sentences, or into clauses at `clause` chunk size.
5. For each sentence, diacritize, then run the backend.

The hook runs before the sentence split. A split of raw text cuts after
`Prof.`, but `text2spoken` writes `Professor` and the split then sees one
sentence.

## Which library runs each stage

| Stage | Library | Extra | How scriptconv calls it |
|---|---|---|---|
| Normalise | [text2spoken](https://github.com/TigreGotico/text2spoken) | `normalize` | `spoken_normalizer()` returns `text2spoken.normalize` for the `normalizer` hook |
| Diacritize Arabic | [text2tashkeel](https://github.com/TigreGotico/text2tashkeel) | `tashkeel` | `scriptconv.diacritics.diacritize(text, "ar")` |
| Diacritize Hebrew | phonikud | `he` | `diacritize(text, "he")` |
| Restore stress | [stressonnx](https://github.com/TigreGotico/stressonnx) | `stress` | `diacritize(text, lang)` for a language in `STRESS_LANGS` |
| Mark Portuguese homographs | [bifonia](https://github.com/TigreGotico/bifonia) | `pt` | `diacritize(text, "pt")`, never for `pt-BR` |
| Phonemize | the backend: orthography2ipa, tugaphone, espeak and others | the extra of the backend | `get_phonemizer` or `phonemizer_for_lang` |

scriptconv does not own normalisation. The hook is off until the caller sets
it. A phonemizer library that reads raw text, such as tugaphone, runs
`text2spoken` in its own pipeline.

## Backends that run a stage themselves

A backend names the stages it runs itself in `owned_stages`, and the frontend
then skips them. tugaphone owns `normalize` and `diacritize`, arbtok owns
`diacritize`, and dizione and euskaphone own `normalize`. A backend that owns
`normalize` gets the text as written, so the caller's hook does not run for
it.

---
[Index](index.md) · [scripts →](scripts.md)
