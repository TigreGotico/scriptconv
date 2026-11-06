# Third-party license notice — iqra_phonetiser

This directory vendors the phonetisation core of `phonetise_Arabic.py` from
[Iqra-Eval/MSA_phonetiser](https://github.com/Iqra-Eval/MSA_phonetiser) — the
IqraEval shared task's own published data-prep code (used, per its
`run_phonetiser.py`, to generate the `phoneme_ref` column of
`IqraEval/Iqra_train`, the corpus `Phonemizer.IQRA` targets).

That file is itself a fork of Nawar Halabi's Arabic-Phonetiser
(https://github.com/nawarhalabi/Arabic-Phonetiser), licensed under the
**Creative Commons Attribution-NonCommercial 4.0 International License**
(https://creativecommons.org/licenses/by-nc/4.0/) — NOT the Apache-2.0 license
of the rest of this repository. `phonetise-Buckwalter.py` in the IqraEval fork
is byte-identical to the original upstream file (`cmp` verified);
`phonetise_Arabic.py` carries small, deliberate patches on top of it (see
`phonetiser.py`'s module docstring for the diff against both the original
upstream and against mantoq's own vendored copy). The IqraEval fork carries no
separate LICENSE file of its own, so the inherited CC BY-NC 4.0 terms govern
it as a derivative work.

Kept in its own quarantine, separate from `../mantoq/` — the two are
independent copies of the same phonetiser family at different patch levels,
each with the specific behavior a different scriptconv edge needs preserved:
`../mantoq/` for `Phonemizer.MANTOQ`'s long-standing, model-compatible
contract; this one for `Phonemizer.HALABI`/`Phonemizer.IQRA`'s fidelity to
`phoneme_ref`. Nothing here imports at package import time; using it is an
explicit per-request opt-in (constructing `HalabiPhonemizer` or
`IqraPhonemizer`) that accepts this directory's license.
