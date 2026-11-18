"""The disk cache of ``TextFrontend.identity``: hits, misses for each key part, and writes."""
import json
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import pytest

from scriptconv.frontend import FrontendConfig, Stages, TextFrontend
from scriptconv.phonemizers import GraphemePhonemizer, PhonemizerIdentity, _identity_cache

ROOT = Path(__file__).resolve().parent.parent


def counted_backend_calls(monkeypatch):
    """The languages of each call of ``GraphemePhonemizer.identity`` from here on."""
    calls = []
    identity = GraphemePhonemizer.identity

    def counted(self, lang):
        calls.append(lang)
        return identity(self, lang)
    monkeypatch.setattr(GraphemePhonemizer, "identity", counted)
    return calls


def frontend(**config):
    return TextFrontend(FrontendConfig("pt-PT", **config), GraphemePhonemizer())


def fake_distribution(directory, name, top="", editable_root=None):
    """A ``<name>-1.0.dist-info`` in *directory*, with *top* as its top-level module."""
    info = directory / f"{name}-1.0.dist-info"
    info.mkdir()
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 1.0\n")
    (info / "RECORD").write_text(f"{info.name}/METADATA,,\n")
    if top:
        (info / "top_level.txt").write_text(f"{top}\n")
    if editable_root is not None:
        (info / "direct_url.json").write_text(json.dumps(
            {"url": editable_root.as_uri(), "dir_info": {"editable": True}}))
    return info


@pytest.fixture
def site(tmp_path, monkeypatch):
    """A ``sys.path`` directory of this test, on the path before the first identity."""
    directory = tmp_path / "site"
    directory.mkdir()
    monkeypatch.syspath_prepend(str(directory))
    return directory


def hit_then(monkeypatch, change):
    """The backend calls of a first identity, a second one, and a third one after *change*."""
    calls = counted_backend_calls(monkeypatch)
    first = frontend().identity()
    second = frontend().identity()
    assert (first.revision is not None, first == second, len(calls)) == (True, True, 1)
    change()
    third = frontend().identity()
    assert third == first
    return len(calls)


@pytest.mark.usefixtures("identity_cache")
class TestKey:
    def test_the_entry_lives_in_the_user_cache_directory(self, tmp_path):
        frontend().identity()
        assert _identity_cache.cache_dir() == tmp_path / "cache" / "scriptconv" / "identity"
        assert len(list(_identity_cache.cache_dir().glob("*.json"))) == 1

    def test_nothing_changed_is_a_hit(self, monkeypatch):
        assert hit_then(monkeypatch, lambda: None) == 1

    def test_a_reinstalled_distribution_is_a_miss(self, monkeypatch, site):
        info = fake_distribution(site, "reinstalled")
        assert hit_then(monkeypatch, lambda: (info / "RECORD").write_text(
            f"{info.name}/METADATA,,\n{info.name}/RECORD,,\n")) == 2

    def test_an_edited_editable_source_file_is_a_miss(self, monkeypatch, site, tmp_path):
        project = tmp_path / "project"
        (project / "editablepkg").mkdir(parents=True)
        module = project / "editablepkg" / "__init__.py"
        module.write_text("ANSWER = 1\n")
        fake_distribution(site, "editablepkg", top="editablepkg", editable_root=project)
        monkeypatch.syspath_prepend(str(project))
        monkeypatch.delitem(sys.modules, "editablepkg", raising=False)
        __import__("editablepkg")
        assert hit_then(monkeypatch, lambda: module.write_text("ANSWER = 42\n")) == 2

    def test_an_edited_checkout_file_on_the_path_is_a_miss(self, monkeypatch, tmp_path):
        checkout = tmp_path / "checkout"
        (checkout / "checkoutpkg").mkdir(parents=True)
        module = checkout / "checkoutpkg" / "__init__.py"
        module.write_text("ANSWER = 1\n")
        monkeypatch.syspath_prepend(str(checkout))
        monkeypatch.delitem(sys.modules, "checkoutpkg", raising=False)
        __import__("checkoutpkg")
        assert hit_then(monkeypatch, lambda: module.write_text("ANSWER = 42\n")) == 2

    def test_an_edited_checkout_that_shadows_an_installed_distribution_is_a_miss(self, monkeypatch, site,
                                                                                tmp_path):
        fake_distribution(site, "shadowpkg", top="shadowpkg")
        (site / "shadowpkg").mkdir()
        (site / "shadowpkg" / "__init__.py").write_text("ANSWER = 0\n")
        checkout = tmp_path / "checkout"
        (checkout / "shadowpkg").mkdir(parents=True)
        module = checkout / "shadowpkg" / "__init__.py"
        module.write_text("ANSWER = 1\n")
        monkeypatch.syspath_prepend(str(checkout))
        monkeypatch.delitem(sys.modules, "shadowpkg", raising=False)
        assert Path(__import__("shadowpkg").__file__) == module
        assert hit_then(monkeypatch, lambda: module.write_text("ANSWER = 42\n")) == 2

    def test_a_new_distribution_in_a_path_directory_is_a_miss(self, monkeypatch, site):
        def install():
            time.sleep(0.05)  # past the timestamp granularity of the file system
            fake_distribution(site, "installed", top="installed")
        assert hit_then(monkeypatch, install) == 2

    def test_another_python_is_a_miss(self, monkeypatch):
        assert hit_then(monkeypatch, lambda: monkeypatch.setattr(sys, "version", "3.99.0 (other)")) == 2

    def test_another_interpreter_path_is_a_miss(self, monkeypatch, tmp_path):
        assert hit_then(monkeypatch, lambda: monkeypatch.setattr(
            sys, "executable", str(tmp_path / "other" / "python"))) == 2

    def test_another_frontend_setting_is_a_miss(self, monkeypatch):
        calls = counted_backend_calls(monkeypatch)
        frontend().identity()
        frontend(keep_punctuation=True).identity()
        TextFrontend(FrontendConfig("es"), GraphemePhonemizer()).identity()
        assert len(calls) == 3

    def test_another_instance_setting_is_a_miss(self, monkeypatch):
        calls = counted_backend_calls(monkeypatch)
        changed = GraphemePhonemizer()
        changed.drop_chars = "<>"
        first = frontend().identity()
        second = TextFrontend(FrontendConfig("pt-PT"), changed).identity()
        assert len(calls) == 2 and first.revision != second.revision


@pytest.mark.usefixtures("identity_cache")
class TestEntries:
    def test_a_corrupt_entry_is_a_miss_and_is_written_again(self, monkeypatch):
        calls = counted_backend_calls(monkeypatch)
        expected = frontend().identity()
        (entry,) = _identity_cache.cache_dir().glob("*.json")
        entry.write_text('{"key": [')
        assert frontend().identity() == expected
        assert frontend().identity() == expected
        assert len(calls) == 2
        assert json.loads(entry.read_text())["identity"]["revision"] == expected.revision

    def test_an_identity_with_no_revision_is_not_kept(self):
        assert frontend(stages=Stages(casing=str.upper)).identity().revision is None
        assert not list(_identity_cache.cache_dir().glob("*"))

    def test_a_cache_directory_that_cannot_be_written_gives_the_identity(self, monkeypatch, tmp_path):
        (tmp_path / "file").write_text("")
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "file"))
        assert frontend().identity().revision is not None

    def test_two_processes_that_write_one_entry_leave_one_whole_entry(self, tmp_path):
        writer = textwrap.dedent("""
            import sys
            from scriptconv.phonemizers import GraphemePhonemizer, PhonemizerIdentity, _identity_cache
            key = {"writer": "test"}
            identity = PhonemizerIdentity("graphemes", "scriptconv", "1", "pt-PT", "sc1:" + sys.argv[1] * 64, 2)
            backend = GraphemePhonemizer()
            for _ in range(40):
                _identity_cache.store(key, identity, backend)
        """)
        writers = [subprocess.Popen([sys.executable, "-c", writer, digit], cwd=tmp_path,
                                    env={**os.environ, "PYTHONPATH": str(ROOT)}) for digit in "12"]
        reads = 0
        while any(process.poll() is None for process in writers):
            for entry in _identity_cache.cache_dir().glob("*.json"):
                try:
                    text = entry.read_text()
                except FileNotFoundError:
                    continue
                json.loads(text)  # a reader never sees half an entry
                reads += 1
        assert [process.wait(timeout=600) for process in writers] == [0, 0]
        assert reads > 0
        entries = list(_identity_cache.cache_dir().iterdir())
        assert len(entries) == 1 and entries[0].suffix == ".json"
        entry = json.loads(entries[0].read_text())
        assert entry["identity"]["revision"] in ("sc1:" + "1" * 64, "sc1:" + "2" * 64)
        assert _identity_cache.load({"writer": "test"}) == PhonemizerIdentity(**entry["identity"])


TUGAPHONE_IDENTITY = """
import json, sys, time
from scriptconv.frontend import FrontendConfig, TextFrontend, spoken_normalizer
from scriptconv.phonemizers.pt import TugaphonePhonemizer
frontend = TextFrontend(FrontendConfig("pt-PT", normalizer=spoken_normalizer()), TugaphonePhonemizer())
if sys.argv[1] == "hit":
    import text2spoken
    from scriptconv.phonemizers import _revision
    def refuse(*args, **kwargs):
        raise AssertionError("a hit runs no probe and does not call the backend")
    _revision._run_probe = text2spoken.revision = TugaphonePhonemizer.identity = refuse
started = time.perf_counter()
identity = frontend.identity()
print(json.dumps({"revision": identity.revision, "seconds": time.perf_counter() - started}))
"""


@pytest.mark.timeout(900)
@pytest.mark.usefixtures("identity_cache")
def test_a_hit_for_a_tugaphone_frontend_with_the_text2spoken_hook_costs_under_50_ms(tmp_path):
    def run(mode):
        # the cache directory is under the working directory, which is on sys.path
        done = subprocess.run([sys.executable, "-c", TUGAPHONE_IDENTITY, mode], cwd=tmp_path, check=True,
                              capture_output=True, text=True, env={**os.environ, "PYTHONPATH": str(ROOT)})
        return json.loads(done.stdout.splitlines()[-1])
    miss = run("miss")
    hits = [run("hit") for _ in range(3)]
    print("miss", miss["seconds"], "hits", [hit["seconds"] for hit in hits])
    assert miss["revision"] is not None and miss["revision"].startswith("sc1:")
    assert all(hit["revision"] == miss["revision"] for hit in hits)
    assert min(hit["seconds"] for hit in hits) < 0.05
