"""QUARANTINED vendored code — NOT covered by scriptconv's Apache-2.0 license.

Each subpackage here is unpublished upstream code vendored for usability,
distributed under ITS OWN license, stated in its directory:

* ``mantoq/`` — Arabic G2P (github.com/mush42/mantoq). Its phonetisation core
  (``buck/phonetise_buckwalter.py``) is **CC BY-NC 4.0** (Nawar Halabi's
  Arabic-Phonetiser) — non-commercial use only. See ``mantoq/LICENSE.md``.
* ``kog2p/`` — Korean G2P (github.com/scarletcho/KoG2P), **GPL-3.0**.
  See ``kog2p/LICENSE.md``.
* ``africa_g2p/`` — African-language G2P (github.com/AfriSpeech/africa-g2p),
  400+ ISO 639-3 rule files. Vendored (not depended on) because it is not
  published to PyPI and this project does not take ``git+`` dependencies.
  Its **code** is Apache-2.0 — same license as the rest of this repository,
  unlike the other two entries here — but its **data** (the ``languages/``
  rule files and ``data/registry.json``) is derived from Omniglot script
  charts (© Simon Ager) and Hartell (ed.), *Alphabets of Africa* (UNESCO/SIL,
  1993), and carries its own attribution requirements. See
  ``africa_g2p/LICENSE.md`` and ``africa_g2p/DATA_LICENSE.md``.

Nothing in scriptconv imports these at package import time; they load only
when a caller explicitly requests the corresponding phonemizer, accepting the
subpackage's license by doing so.  Unencumbered alternatives exist for both
(arbtok for Arabic, g2pk for Korean) and remain the defaults.
"""
