# Orthographic conventions — `scriptconv.conventions`

Two pieces of Arabic text can be the same words with and without vowel marks.
Japanese can be written solid or with spaces between words. Pinyin writes
tone as diacritics or as digits. None of these differences change what script
the text is in — they are **decorations** a script's orthography can carry or
omit. This module models them as first-class data, with one uniform algebra
for adding, removing, and restyling them.

The distinction that shapes the whole design: **scripts are identity,
conventions are parameters.** A convention never participates in script
detection and is never a node in the conversion graph — otherwise every
representation would split into one node per decoration state.

## The algebra

Every convention declares its *styles* — the mutually exclusive states its
text can be in. Binary decorations have styles `("marked", "none")`; variant
conventions name their spellings (`("mark", "number", "none")`). The one real
operation is `restyle`, a transition between styles; everything else is sugar:

```python
from scriptconv import strip, apply, restyle, detect_convention, conventions_for

strip("مُحَمَّد", "tashkeel")          # 'محمد'         restyle to "none"
restyle("zhong1", "pinyin-tone", "mark")   # 'zhōng'
detect_convention("مُحَمَّد", "tashkeel")   # 'marked'
[c.id for c in conventions_for("Hebr")]   # ['niqqud', 'teamim']
```

Which transitions exist follows one criterion, applied uniformly:

- **Deterministic re-spelling** (stripping marks, converting tone digits to
  diacritics) is always available, zero-dependency.
- **Dictionary lookup** (applying wakachigaki requires word segmentation) is
  in scope but behind an extra, mirroring [readings](readings.md).
- **Contextual prediction** (restoring stripped tashkeel or niqqud) is out of
  scope entirely — that is diacritization, a modelling problem. Its absence
  is a queryable fact of the registry, not a runtime surprise.

Unsupported transitions raise `ValueError` listing the supported ones; a
transition whose backing extra is missing raises `ImportError` naming it.

## The registry

| id | script(s) | styles | notes |
|---|---|---|---|
| `tashkeel` | Arab | marked/none | harakat, tanwin, shadda, sukun, dagger alef |
| `kashida` | Arab | marked/none | tatweel justification — its own layer, not vocalization |
| `quranic-marks` | Arab | marked/none | annotation signs; structural signs (end-of-ayah) survive |
| `niqqud` | Hebr | marked/none | points incl. dagesh, meteg, rafe, shin/sin dots |
| `teamim` | Hebr | marked/none | cantillation — a separate layer from niqqud |
| `wakachigaki` | Hira, Kana, Hani | marked/none | Japanese word spacing |
| `pinyin-tone` | Latn (pinyin) | mark/number/none | tone spelling styles |
| `jamo-form` | Hang | compatibility/conjoining | Unicode jamo repertoires |

Worked examples across the registry:

```python
strip("שָׁלוֹם", "niqqud")                          # 'שלום'
strip("וַ֑יֹּאמֶר", "teamim")                        # cantillation gone, vowels kept
strip("わたし は がくせい です", "wakachigaki")      # 'わたしはがくせいです'
strip("محمـــد", "kashida")                       # 'محمد'
restyle("zhōng guó", "pinyin-tone", "number", frm="mark")   # 'zhong1 guo2'
restyle("ㄱㅏㅁ", "jamo-form", "conjoining")        # conjoining jamo — renders composed as '감'
```

## Linguistic care baked into the tables

The codepoint sets are curated against real failure modes, not just block
ranges:

- **Tashkeel excludes U+0653–0655** (madda, hamza above, hamza below). In
  decomposed text those combining marks *are* the letters آ / أ / إ; a
  blanket strip corrupts the consonantal skeleton. Decomposed Arabic
  round-trips with its hamzas intact.
- **Niqqud and teamim are separate layers**, as in Masoretic practice; maqaf
  and sof pasuq are punctuation and survive both strips. Stripping the
  shin/sin dots loses the שׁ/שׂ distinction — exactly as unpointed Hebrew
  does, and the registry says so.
- **Wakachigaki stripping is flank-conservative**: a space is removed only
  when *both* neighbors are Japanese characters. "きょうは good day" and
  "第 3 章" keep their spaces, because those spaces carry information.
- **Pinyin tone restyling is deterministic both ways** for standard
  apostrophized pinyin (mark placement follows the a/e-first rule; `ü`
  accepts the `v` and `u:` input spellings; erhua and syllabic nasals like
  `ḿ` are handled). On non-apostrophized input, digit placement is
  best-effort and documented as such.
- **`jamo-form` is a Unicode representation convention** rather than an
  orthographic one — registered because free text genuinely occurs in both
  repertoires, and stated as the registry's one deliberate boundary
  exception. Compatibility jamo don't distinguish onset from coda, so the
  conjoining direction resolves position from context.

What is *not* a convention: marks that are letter identity. Vietnamese tone
diacritics spell different words; stripping them is corruption, not
undecoration, and no such operation exists here. Casing on bicameral scripts
fits the concept but is already modelled correctly by `str.lower` /
`str.casefold`, so it is deliberately not duplicated.
