import pytest

from scriptconv.phonemizers import _identity_cache

_LOAD = _identity_cache.load
_CACHE_DIR = _identity_cache.cache_dir


@pytest.fixture(autouse=True)
def _isolated_identity_cache(tmp_path, monkeypatch):
    """An identity cache directory of its own for each test, and no entry read
    in this process. A test that mocks an input of a revision would otherwise
    read the entry of an earlier call. The user cache directory stays as it
    is, because the diacritizers keep their models there."""
    monkeypatch.setattr(_identity_cache, "cache_dir", lambda: tmp_path / "identity")
    monkeypatch.setattr(_identity_cache, "load", lambda entry_key: None)


@pytest.fixture
def identity_cache(tmp_path, monkeypatch):
    """The identity cache, read as in production, under a user cache directory
    of this test that a fresh process inherits."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setattr(_identity_cache, "cache_dir", _CACHE_DIR)
    monkeypatch.setattr(_identity_cache, "load", _LOAD)
    return _identity_cache.cache_dir()
