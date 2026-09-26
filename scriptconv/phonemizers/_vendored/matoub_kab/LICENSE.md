# Third-party license notice — Matoub-82M Kabyle rules

Vendored from https://huggingface.co/agbalu/Matoub-82M, file
`tokenization_matoub.py`, revision `3d00056f3663d4d1d364e9b12c21230685a0ba9a`,
sha256 `c95fdf4bd23efa649287662a0059d9053d17c8cab4fade383784e084cc422416`.

Licensed **Apache-2.0**, the same licence this repository uses, so this
directory adds no new licence obligation. The model card records the licence as
`apache-2.0`.

Only the rule functions are vendored. The upstream `MatoubTokenizer` class,
which subclasses `transformers.PreTrainedTokenizer`, is not included, so this
directory imports nothing outside the standard library.
