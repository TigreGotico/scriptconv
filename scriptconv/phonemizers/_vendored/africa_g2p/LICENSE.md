# Third-party license notice — africa-g2p

Vendored from https://github.com/AfriSpeech/africa-g2p at tag `v0.2.4`
(commit e3642dea), the release published to PyPI as `africa-g2p` 0.2.4.
Every file except this one is byte-identical to `src/africa_g2p/` at that
commit (the `data/*.json.survey` build artefact is not copied: nothing
reads it at runtime). The **code**
(`g2p.py`, `loader.py`, `normalizer.py`, `pipeline.py`, `cli.py`,
`convert.py`, `english.py`, `fallback.py`, `__init__.py`) is
**Apache-2.0**, same as the rest of this repository —
unlike `mantoq/` and `kog2p/`, this subpackage's code carries no extra
restriction beyond scriptconv's own license.

The **data** under `languages/` and `data/registry.json` is NOT
Apache-2.0: it is derived from third-party sources (Omniglot script
charts, © Simon Ager; Hartell 1993/UNESCO's *Alphabets of Africa*) and
carries its own attribution requirements — see `DATA_LICENSE.md` in this
directory. Redistributing the language data must keep those
attributions.

`data/ipa_universal_graphemes.json` is not chart data: upstream built it
from a survey of the rule tables and curated it with an LLM (upstream
commit 4784edd, "Curate universal graphemes via Gemini"). Only the
cross-language converter (`convert.py`, `convert_to_ipa`) reads it. The
per-language pipeline that scriptconv's `AfricaG2PPhonemizer` calls
(`AfricaPipeline`) does not.

Upstream `master` after `v0.2.4` adds 238 rule tables marked
`"confidence": "llm-draft"` (drafted by an LLM from corpus statistics).
They are not vendored here: this copy carries only the 400 chart-sourced
tables of the release.
