"""The built wheel holds only files under Apache-2.0 or MIT.

The wrappers under a copyleft or a non-commercial licence are in the
scriptconv-copyleft and scriptconv-nonfree packages. This test builds the
wheel from a copy of the source tree and reads every file in it.
"""
import gzip
import re
import shutil
import subprocess
import sys
import zipfile
from email.parser import Parser
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
EXPRESSION = "Apache-2.0 AND MIT AND LicenseRef-CMUdict"
# LicenseRef-CMUdict is the CMUdict licence: BSD-2-Clause with one added
# sentence and an acknowledgement, so no SPDX identifier matches it.
PERMISSIVE = {"Apache-2.0", "MIT", "LicenseRef-CMUdict"}
# Text that each licence notice holds.
NOTICE_TEXT = {"MIT": ("MIT License",),
               "Apache-2.0": ("Apache-2.0", "Apache License, Version 2.0"),
               "LicenseRef-CMUdict": ("Carnegie Mellon University",
                                      "Redistribution and use in source and binary forms")}

# Every file in these directories is first-party or third-party code, and a
# third-party file must be listed below with its licence.
VENDORED = ("scriptconv/data/", "scriptconv/phonemizers/_thirdparty/",
            "scriptconv/phonemizers/_vendored/")
FIRST_PARTY = {
    "scriptconv/data/__init__.py",
    "scriptconv/phonemizers/_thirdparty/__init__.py",
    "scriptconv/phonemizers/_thirdparty/bw2ipa.py",
    "scriptconv/phonemizers/_vendored/__init__.py",
}
CANGJIE5 = "scriptconv/data/LICENSE.cangjie5"
HANGUL_TO_IPA = "scriptconv/phonemizers/_thirdparty/LICENSE.hangul_to_ipa"
F5TTS = "scriptconv/phonemizers/_thirdparty/LICENSE.f5tts"
MATOUB = "scriptconv/phonemizers/_vendored/matoub_kab/LICENSE.md"
DIZIONE = "scriptconv/phonemizers/_thirdparty/dizione/LICENSE"
CMUDICT = "scriptconv/phonemizers/_thirdparty/dizione/built/LICENSE.cmudict"
HOMOGRAPH_DATA = "scriptconv/phonemizers/_thirdparty/dizione/built/LICENSE.homograph-data"
G2PW = "scriptconv/phonemizers/_thirdparty/g2pw/LICENSE"
NAKDIMON = "scriptconv/phonemizers/_thirdparty/nakdimon/LICENSE"
# path prefix -> (licences, the notice the wheel carries for each licence). The
# first prefix that matches a file gives its licences. homographs.json takes
# CMUdict pronunciations for most of its senses.
THIRD_PARTY = {
    "scriptconv/data/cangjie5_tc.tsv.gz": (("MIT", CANGJIE5),),
    "scriptconv/phonemizers/_thirdparty/dizione/built/homographs.json":
        (("Apache-2.0", HOMOGRAPH_DATA), ("LicenseRef-CMUdict", CMUDICT)),
    "scriptconv/phonemizers/_thirdparty/dizione/built/sources.json": (("Apache-2.0", DIZIONE),),
    "scriptconv/phonemizers/_thirdparty/dizione/built/": (("LicenseRef-CMUdict", CMUDICT),),
    "scriptconv/phonemizers/_thirdparty/dizione/": (("Apache-2.0", DIZIONE),),
    "scriptconv/phonemizers/_thirdparty/f5tts.py": (("MIT", F5TTS),),
    "scriptconv/phonemizers/_thirdparty/g2pw/": (("Apache-2.0", G2PW),),
    "scriptconv/phonemizers/_thirdparty/hangul2ipa.py": (("MIT", HANGUL_TO_IPA),),
    "scriptconv/phonemizers/_thirdparty/ko_tables/": (("MIT", HANGUL_TO_IPA),),
    "scriptconv/phonemizers/_thirdparty/nakdimon/": (("MIT", NAKDIMON),),
    "scriptconv/phonemizers/_thirdparty/shami/": (("Apache-2.0", None),),
    "scriptconv/phonemizers/_thirdparty/vosk_g2p.py": (("Apache-2.0", None),),
    "scriptconv/phonemizers/_thirdparty/zh_num.py": (("Apache-2.0", None),),
    "scriptconv/phonemizers/_vendored/matoub_kab/": (("Apache-2.0", MATOUB),),
}

# The text of a restricted licence, in any file.
RESTRICTED_TEXT = re.compile(
    r"GNU (Lesser |Affero |Library )?General Public License|Attribution-NonCommercial"
    r"|creativecommons\.org/licenses/by-nc", re.IGNORECASE)
# A restricted licence named in a licence file.
RESTRICTED_NAME = re.compile(r"\b[AL]?GPL\b|\bGPL-|CC[- ]BY-NC|non-?commercial", re.IGNORECASE)


@pytest.fixture(scope="module")
def wheel(tmp_path_factory):
    source = tmp_path_factory.mktemp("source")
    for name in ("pyproject.toml", "README.md", "LICENSE"):
        shutil.copy(ROOT / name, source / name)
    shutil.copytree(ROOT / "scriptconv", source / "scriptconv",
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    out = tmp_path_factory.mktemp("wheel")
    build = subprocess.run(
        [sys.executable, "-c",
         "import sys; from setuptools import build_meta; print(build_meta.build_wheel(sys.argv[1]))",
         str(out)], cwd=source, capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    return zipfile.ZipFile(out / build.stdout.strip().splitlines()[-1])


def _dist_info(wheel):
    return next(n.split("/")[0] for n in wheel.namelist() if n.endswith(".dist-info/METADATA"))


def _text(wheel, name):
    data = wheel.read(name)
    if name.endswith(".gz"):
        data = gzip.decompress(data)
    return data.decode("utf-8", "ignore")


def _third_party(name):
    return next((value for prefix, value in THIRD_PARTY.items() if name.startswith(prefix)), None)


def test_the_metadata_declares_the_licence_expression(wheel):
    metadata = Parser().parsestr(wheel.read(f"{_dist_info(wheel)}/METADATA").decode())
    assert metadata["License-Expression"] == EXPRESSION
    assert not [c for c in metadata.get_all("Classifier") or [] if c.startswith("License ::")]


def test_every_vendored_file_declares_a_permissive_licence(wheel):
    notices = {notice for licences in THIRD_PARTY.values() for _, notice in licences}
    vendored = [n for n in wheel.namelist()
                if n.startswith(VENDORED) and n not in FIRST_PARTY and n not in notices]
    assert vendored
    assert [n for n in vendored if _third_party(n) is None] == []
    assert {licence for n in vendored for licence, _ in _third_party(n)} <= PERMISSIVE


def test_the_wheel_carries_each_third_party_notice(wheel):
    licences = f"{_dist_info(wheel)}/licenses/"
    for licence, notice in (pair for licences in THIRD_PARTY.values() for pair in licences):
        if notice is not None:
            text = _text(wheel, licences + notice)
            assert any(name in text for name in NOTICE_TEXT[licence]), notice


def test_no_file_holds_a_restricted_licence(wheel):
    found = {}
    for name in wheel.namelist():
        text = _text(wheel, name)
        basename = name.rsplit("/", 1)[-1]
        is_licence = "/licenses/" in name or basename.startswith(("LICENSE", "COPYING", "NOTICE"))
        match = RESTRICTED_TEXT.search(text) or (is_licence and RESTRICTED_NAME.search(text))
        if match:
            found[name] = match.group(0)
    assert found == {}
