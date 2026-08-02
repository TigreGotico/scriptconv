# Third-party license notice — africa-g2p

Vendored from https://github.com/AfriSpeech/africa-g2p (not published to
PyPI, so pinned in-tree rather than depended on). The **code**
(`g2p.py`, `loader.py`, `normalizer.py`, `pipeline.py`, `cli.py`,
`__init__.py`) is **Apache-2.0**, same as the rest of this repository —
unlike `mantoq/` and `kog2p/`, this subpackage's code carries no extra
restriction beyond scriptconv's own license.

The **data** under `languages/` and `data/registry.json` is NOT
Apache-2.0: it is derived from third-party sources (Omniglot script
charts, © Simon Ager; Hartell 1993/UNESCO's *Alphabets of Africa*) and
carries its own attribution requirements — see `DATA_LICENSE.md` in this
directory. Redistributing the language data must keep those
attributions.
