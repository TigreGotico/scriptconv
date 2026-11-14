"""The goruut wrapper stops the local server that it starts.

pygoruut starts a goruut server binary as a child process. The server PIDs in
these tests come from the process tree in /proc, not from the wrapper, so a
wrapper that loses track of its server cannot pass. Every test also stops the
servers it found, so a failing run leaves no orphan behind.
"""
import gc
import os
import signal
import subprocess
import sys
import textwrap
import time
import unittest

from scriptconv.phonemizers.mul import GoruutPhonemizer


def _children(pid: int) -> set:
    children = set()
    for task in os.listdir(f"/proc/{pid}/task"):
        with open(f"/proc/{pid}/task/{task}/children") as fh:
            children.update(int(c) for c in fh.read().split())
    return children


def _is_goruut(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/cmdline", "rb") as fh:
            return b"goruut" in fh.read().split(b"\0")[0]
    except FileNotFoundError:
        return False


def _running(pid: int) -> bool:
    try:
        with open(f"/proc/{pid}/stat") as fh:
            state = fh.read().rsplit(")", 1)[1].split()[0]
    except FileNotFoundError:
        return False
    return state != "Z"


def _stopped(pid: int, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _running(pid):
            return True
        time.sleep(0.1)
    return False


class TestGoruutServerLifetime(unittest.TestCase):
    def _kill_if_running(self, pid: int) -> None:
        if _running(pid) and _is_goruut(pid):
            os.kill(pid, signal.SIGKILL)

    def _new_server(self, before: set) -> int:
        servers = [pid for pid in _children(os.getpid()) - before if _is_goruut(pid)]
        self.assertEqual(len(servers), 1, servers)
        self.addCleanup(self._kill_if_running, servers[0])
        return servers[0]

    def test_server_stops_when_the_process_exits(self):
        code = textwrap.dedent("""
            import sys
            from scriptconv.phonemizers.mul import GoruutPhonemizer
            phonemizer = GoruutPhonemizer()
            print("ready", flush=True)
            sys.stdin.readline()
        """)
        child = subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.PIPE,
                                 stdout=subprocess.PIPE, text=True)
        self.addCleanup(child.stdout.close)
        self.addCleanup(child.kill)
        self.assertEqual(child.stdout.readline().strip(), "ready")
        servers = [pid for pid in _children(child.pid) if _is_goruut(pid)]
        self.assertEqual(len(servers), 1, servers)
        self.addCleanup(self._kill_if_running, servers[0])

        # The server inherits the child's stdout, so reading it to EOF would
        # wait for the server too. Wait for the child process only.
        child.stdin.write("\n")
        child.stdin.close()
        self.assertEqual(child.wait(timeout=60), 0)
        self.assertTrue(_stopped(servers[0]),
                        f"goruut server {servers[0]} outlived its process")

    def test_close_stops_the_server(self):
        before = _children(os.getpid())
        phonemizer = GoruutPhonemizer()
        server = self._new_server(before)
        self.assertTrue(_running(server))
        phonemizer.close()
        self.assertTrue(_stopped(server))
        phonemizer.close()

    def test_garbage_collection_stops_only_its_own_server(self):
        before = _children(os.getpid())
        local = GoruutPhonemizer()
        server = self._new_server(before)
        url = local.pygoruut.config.url("").rstrip("/")
        remote = GoruutPhonemizer(remote_url=url)
        self.assertTrue(remote.phonemize_string("hello", "en"))
        remote.close()
        del remote
        gc.collect()
        self.assertFalse(_stopped(server, timeout=1.0))
        self.assertTrue(local.phonemize_string("hello", "en"))

        del local
        gc.collect()
        self.assertTrue(_stopped(server))


if __name__ == "__main__":
    unittest.main()
