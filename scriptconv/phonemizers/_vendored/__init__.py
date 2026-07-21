"""QUARANTINED vendored code — NOT covered by scriptconv's Apache-2.0 license.

Each subpackage here is unpublished upstream code vendored for usability,
distributed under ITS OWN license, stated in its directory:

* ``mantoq/`` — Arabic G2P (github.com/mush42/mantoq). Its phonetisation core
  (``buck/phonetise_buckwalter.py``) is **CC BY-NC 4.0** (Nawar Halabi's
  Arabic-Phonetiser) — non-commercial use only. See ``mantoq/LICENSE.md``.
* ``kog2p/`` — Korean G2P (github.com/scarletcho/KoG2P), **GPL-3.0**.
  See ``kog2p/LICENSE.md``.

Nothing in scriptconv imports these at package import time; they load only
when a caller explicitly requests the corresponding phonemizer, accepting the
subpackage's license by doing so.  Unencumbered alternatives exist for both
(arbtok for Arabic, g2pk for Korean) and remain the defaults.
"""
