"""Every licence notice under ``_vendored`` is declared as package data."""
import fnmatch
import pathlib
import unittest

try:
    import tomllib
except ModuleNotFoundError:  # tomllib is stdlib only from Python 3.11
    import tomli as tomllib

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_VENDORED = _ROOT / "scriptconv" / "phonemizers" / "_vendored"


class TestVendoredLicencesShip(unittest.TestCase):
    def test_every_notice_is_package_data(self):
        package_data = tomllib.loads((_ROOT / "pyproject.toml").read_text(
            encoding="utf-8"))["tool"]["setuptools"]["package-data"]
        notices = sorted(_VENDORED.glob("*/*LICENSE*.md"))
        self.assertTrue(notices)
        for notice in notices:
            package = ".".join(notice.parent.relative_to(_ROOT).parts)
            with self.subTest(package=package, notice=notice.name):
                patterns = package_data.get(package, [])
                self.assertTrue(
                    any(fnmatch.fnmatch(notice.name, p) for p in patterns),
                    f"{notice.name} of {package} is not in package-data, "
                    f"so the wheel ships the code without its notice")


if __name__ == "__main__":
    unittest.main()
