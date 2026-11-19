"""The whole tool from the command line, on the synthetic data, as a reader would run it."""
from __future__ import annotations

import json
import os
import re
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import support  # first: it puts src/ on the path

GARDEN = [sys.executable, str(support.ROOT / "src" / "garden.py")]
FEEDS = support.EXAMPLES / "sources"


def garden(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*GARDEN, *args], capture_output=True, text=True, env=env, timeout=60)


class DemoTest(unittest.TestCase):
    def test_run_sh_prints_the_expected_output(self) -> None:
        done = subprocess.run(["bash", str(support.EXAMPLES / "run.sh")],
                              capture_output=True, text=True, check=True)
        expected = (support.EXAMPLES / "expected-output.txt").read_text(encoding="utf-8")
        self.assertEqual(done.stdout, expected)

    def test_the_readme_preview_is_the_demo_output(self) -> None:
        readme = (support.ROOT / "README.md").read_text(encoding="utf-8")
        board = garden("--demo").stdout
        self.assertIn(board, readme)

    def test_demo_collect_writes_nothing(self) -> None:
        done = garden("--demo", "collect")
        self.assertEqual(done.returncode, 0)
        self.assertIn("demo: nothing written", done.stdout)

    def test_the_demo_never_changes_herdr(self) -> None:
        done = garden("--demo", "tab", "--apply", env=os.environ | {"HERDR_ENV": "1"})
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("never changes Herdr", done.stderr)

    def test_an_unknown_key_says_how_to_find_one(self) -> None:
        done = garden("--demo", "prompt", "diff", "acme/nothing")
        self.assertIn("no item acme/nothing", done.stderr)


class OwnConfigTest(unittest.TestCase):
    """A reader's own config, with the example feeds as local files and a stand-in herdr."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.herdr, self.log = support.fake_herdr(self.dir)
        self.config = support.write_toml(self.dir, f"""
            title = "my garden"
            interests = ["agent", "terminal", "test", "python", "api"]
            board = "state/board.json"
            [filter]
            min_stars = 5
            drop = ["airdrop"]
            [handoff]
            mode = "herdr"
            agent = "scout"
            herdr = {json.dumps(str(self.herdr))}
            [[sources]]
            type = "github-search"
            query = "unused"
            path = {json.dumps(str(FEEDS / "github-search.json"))}
            [[sources]]
            type = "rss"
            path = {json.dumps(str(FEEDS / "dev-news.rss"))}
            [[sources]]
            type = "rss"
            path = "missing.rss"
        """)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_garden(self, *args: str, **env: str) -> subprocess.CompletedProcess[str]:
        clean_env = {k: v for k, v in os.environ.items() if k not in ("HERDR_ENV", "GARDEN_CONFIG")}
        return garden("--config", str(self.config), "--today", support.TODAY, *args,
                      env=clean_env | {"FAKE_HERDR_LOG": str(self.log)} | env)

    def test_collect_then_board_then_send(self) -> None:
        done = self.run_garden("collect")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("missing.rss: FAILED: cannot read missing.rss", done.stdout)
        board = json.loads((self.dir / "state" / "board.json").read_text(encoding="utf-8"))
        self.assertEqual(len(board["items"]), 9)
        self.assertFalse((self.dir / "state" / "board.json.tmp").exists())

        shown = self.run_garden("board").stdout
        self.assertIn("my garden · 2026-01-15 · 9 kept", shown)
        self.assertIn("source failed: missing.rss", shown)

        refused = self.run_garden("send", "diff", "acme/tdd-skill")
        self.assertEqual(refused.returncode, 1)
        self.assertIn("HERDR_ENV", refused.stderr)
        self.assertFalse(self.log.exists())  # outside Herdr, herdr is never called

        sent = self.run_garden("send", "diff", "acme/tdd-skill", HERDR_ENV="1")
        self.assertEqual(sent.returncode, 0, sent.stderr)
        call = json.loads(self.log.read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(call[:3], ["agent", "prompt", "scout"])
        self.assertIn("https://github.com/acme/tdd-skill", call[3])

    def test_board_before_collect_says_what_to_do(self) -> None:
        done = self.run_garden("board")
        self.assertNotEqual(done.returncode, 0)
        self.assertIn("run python3 src/garden.py collect", done.stderr)


@unittest.skipUnless(sys.platform.startswith(("linux", "darwin")), "needs a Unix pseudo-terminal")
class PaneInTerminalTest(unittest.TestCase):
    """Start the real pane in a private pseudo-terminal, press keys, and quit."""

    def test_the_pane_draws_shows_a_prompt_and_quits(self) -> None:
        import fcntl
        import pty
        import struct
        import termios

        pid, fd = pty.fork()
        if pid == 0:  # the child: become the pane
            os.environ["TERM"] = "xterm-256color"
            os.environ.pop("HERDR_ENV", None)
            os.execv(sys.executable, [*GARDEN, "--demo", "pick"])
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", 30, 100, 0, 0))
        out = b""

        def pump(seconds: float) -> None:
            nonlocal out
            end = time.time() + seconds
            while time.time() < end:
                ready, _, _ = select.select([fd], [], [], 0.05)
                if ready:
                    try:
                        out += os.read(fd, 65536)
                    except OSError:
                        return

        try:
            pump(1.5)
            for key in (b"j", b"4", b"d"):
                os.write(fd, key)
                pump(0.4)
            os.write(fd, b"q")
            pump(1.0)
        finally:
            _, status = os.waitpid(pid, 0)
            os.close(fd)
        screen = re.sub(rb"\x1b\[[0-9;?]*[A-Za-z]|\x1b[()][0-9A-B]|\x1b[=>]", b" ", out).decode("utf-8", "replace")
        self.assertEqual(os.waitstatus_to_exitcode(status), 0, screen[-500:])
        self.assertIn("demo garden", screen)
        self.assertIn("Prompt (not sent", screen)
        self.assertNotIn("Traceback", screen)


if __name__ == "__main__":
    unittest.main()
