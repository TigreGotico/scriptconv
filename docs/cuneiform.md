# `cuneiform` — signs and the names Unicode gives them

Assyriology writes a cuneiform text twice: once in the signs, and once in a
Latin transliteration that names each sign. The Unicode Standard carries one
of those names for every sign it encodes, and this module converts between the
two.

```python
from scriptconv import cuneiform_to_sign_names, sign_names_to_cuneiform

cuneiform_to_sign_names("𒀭 𒈗 𒂍")   # 'AN LUGAL E2'
sign_names_to_cuneiform("AN LUGAL")   # '𒀭𒈗'
```

## Sign values, not readings

This is the one thing to be clear about before using it. A sign has many
readings. `𒀭` is read `an`, `dingir` or `il` depending on the word it stands
in, and Akkadian, Sumerian and Hittite disagree about the same sign. Choosing
between readings is a question about the *language*, answered with a lexicon
and a context — not a question about the writing system.

Unicode's name records the conventional sign value only, which is the value
the field writes in capitals, so that is what converts here. A converter that
guessed a reading would produce fluent-looking transliteration that is wrong
in ways only an Assyriologist would catch.

## What survives a round trip

Every encoded sign has exactly one Unicode name, and no two signs share one,
so a sequence of signs converts out and back unchanged.

Two things do not survive. Spacing is not carried: sign names have to be
separated from each other and signs do not, so the two directions cannot agree
on what a space meant. And a name Unicode never assigned has no sign to
become — such input follows the usual `errors` policy
(`pass`, `replace`, `ignore`, `strict`).

## Where the table comes from

There is no table in the wheel. The mapping is read out of `unicodedata` at
import, so it is the standard's own data rather than a copy that can drift,
and it follows whatever Unicode version the interpreter was built against. A
sign encoded after that version simply does not convert, rather than
converting wrongly.

Covered blocks: Cuneiform (U+12000–U+123FF), Cuneiform Numbers and
Punctuation (U+12400–U+1247F), and Early Dynastic Cuneiform
(U+12480–U+1254F).

## Readings, behind an optional install

Everything above converts sign *values*. Actual Assyriological
transliteration writes *readings* — `a-na`, `dan-nu`, `LUGAL` — and going from
those to signs needs a reading list, which is a scholarly artifact rather than
something derivable. scriptconv ships none.

[`cuneiscribe`](https://pypi.org/project/cuneiscribe/) publishes one: 14,240
readings over 1,779 sign sequences. Install it and the edge appears:

```python
# pip install 'scriptconv[cuneiscribe]'
from scriptconv import readings_to_cuneiform

readings_to_cuneiform("a-na")            # '𒀀𒈾'
readings_to_cuneiform("a-na KUR as-sur")  # '𒀀𒈾 𒆳 𒊍𒋩'
```

Readings are separated by hyphens or dots inside a word, words by spaces, and
each word's signs are written without separators. Determinatives are dropped:
`{d}` before a divine name is a silent classifier, not a sign.

The package is installed for its bundled data file and nothing else. Its
top-level import pulls in torch and transformers, which is a great deal of
machinery for reading a JSON file, so scriptconv locates the package without
executing it and reads the file from disk. Nothing is copied into this
package, so the table's terms stay its own — the same arrangement the
phonemizer engines have.

An unknown reading follows the `errors` policy rather than being guessed at.
`cuneiscribe`'s own lookup falls back to stripping index digits, so an unknown
`u₂` returns the sign for `u` — a different sign, silently. An index digit is
part of a reading's identity, not decoration on it.

This direction only. 1505 of the 1779 sign sequences carry more than one
reading, so going back is a question about the language, and
`cuneiform_to_sign_names` is the reverse that has a single answer.

## In the graph

The representations are `cuneiform` (script `Xsux`), `sign-names` and
`sign-readings` (both script `Latn`). The sign direction is registered
lossless; the name direction is not, for the reason above, and the readings
edge declares `requires="cuneiscribe"`.

```python
from scriptconv import DEFAULT_GRAPH

DEFAULT_GRAPH.convert("𒀭", "cuneiform", "sign-names")   # 'AN'
```

## Reference

The Unicode Standard, "Cuneiform", "Cuneiform Numbers and Punctuation", and
"Early Dynastic Cuneiform".
