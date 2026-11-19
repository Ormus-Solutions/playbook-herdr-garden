"""The Garden tab: the plan, and --apply against a stand-in herdr (never the real one)."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

import support  # first: it puts src/ on the path
from feedgarden import herdr_tab

REPO = Path("/srv/acme-web/playbook-herdr-garden")
CONFIG = Path("/srv/acme-web/garden config.toml")


class PlanTest(unittest.TestCase):
    def test_the_four_commands(self) -> None:
        steps = herdr_tab.plan("herdr", REPO, CONFIG, "garden", "codex", "Garden", "w2")
        self.assertEqual(steps, [
            ["herdr", "tab", "create", "--workspace", "w2", "--label", "Garden", "--cwd", str(REPO), "--no-focus"],
            ["herdr", "pane", "split", "<picker-pane>", "--direction", "right", "--cwd", str(REPO), "--no-focus"],
            ["herdr", "pane", "run", "<picker-pane>",
             "python3 src/garden.py --config '/srv/acme-web/garden config.toml' pick"],
            ["herdr", "agent", "start", "garden", "--kind", "codex", "--pane", "<agent-pane>"],
        ])

    def test_no_workspace_flag_outside_a_workspace(self) -> None:
        steps = herdr_tab.plan("herdr", REPO, CONFIG, "garden", "claude", "Garden")
        self.assertNotIn("--workspace", steps[0])

    def test_the_printed_plan_quotes_for_a_shell(self) -> None:
        text = herdr_tab.plan_text(herdr_tab.plan("herdr", REPO, CONFIG, "garden", "claude", "Garden"))
        self.assertIn("herdr pane split '<picker-pane>' --direction right", text)
        self.assertIn(".result.root_pane.pane_id", text)
        self.assertTrue(text.endswith("tab --apply\n"))


class ApplyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.herdr, self.log = support.fake_herdr(Path(self.tmp.name))
        self.steps = herdr_tab.plan(str(self.herdr), REPO, CONFIG, "garden", "claude", "Garden")
        self.said: list[str] = []
        # A stand-in "claude" on PATH, so the --kind check passes on any machine.
        self.bin = Path(self.tmp.name) / "bin"
        self.bin.mkdir()
        agent = self.bin / "claude"
        agent.write_text("#!/bin/sh\n", encoding="utf-8")
        agent.chmod(agent.stat().st_mode | stat.S_IXUSR)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def env(self, **extra: str) -> dict[str, str]:
        env = support.herdr_env(self.log, **extra)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "")
        return env

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_each_id_comes_from_the_reply_before(self) -> None:
        ids = herdr_tab.apply(self.steps, self.env(), say=self.said.append)
        self.assertEqual(ids, {"<picker-pane>": "w1:p9", "<tab>": "w1:t5", "<agent-pane>": "w1:p10"})
        calls = self.calls()
        self.assertEqual(calls[1][:3], ["pane", "split", "w1:p9"])
        self.assertEqual(calls[2][:3], ["pane", "run", "w1:p9"])
        self.assertEqual(calls[3], ["agent", "start", "garden", "--kind", "claude", "--pane", "w1:p10"])
        self.assertIn("To remove it: herdr tab close w1:t5", self.said)

    def test_it_refuses_outside_herdr_and_runs_nothing(self) -> None:
        env = self.env()
        del env["HERDR_ENV"]
        with self.assertRaisesRegex(herdr_tab.TabError, "HERDR_ENV"):
            herdr_tab.apply(self.steps, env, say=self.said.append)
        self.assertEqual(self.calls(), [])

    def test_it_stops_at_the_first_failed_step(self) -> None:
        env = self.env(FAKE_HERDR_FAIL="agent start")
        with self.assertRaisesRegex(herdr_tab.TabError, r"step 4 failed \(agent_not_ready\)"):
            herdr_tab.apply(self.steps, env, say=self.said.append)
        self.assertEqual(len(self.calls()), 4)

        self.log.unlink()
        env = self.env(FAKE_HERDR_FAIL="tab create")
        with self.assertRaisesRegex(herdr_tab.TabError, "step 1 failed") as caught:
            herdr_tab.apply(self.steps, env, say=self.said.append)
        self.assertEqual(len(self.calls()), 1)  # nothing after the failed step ran
        self.assertNotIn("tab close", str(caught.exception))  # no tab was made

    def test_a_half_built_tab_is_named_with_the_way_out(self) -> None:
        # Step 4: the agent waits on a first-run question. The tab is there; a
        # second tab --apply would only make another one.
        with self.assertRaises(herdr_tab.TabError) as caught:
            herdr_tab.apply(self.steps, self.env(FAKE_HERDR_FAIL="agent start"), say=self.said.append)
        message = str(caught.exception)
        self.assertIn("tab w1:t5", message)
        self.assertIn("herdr agent wait garden --until idle", message)
        self.assertIn("Do not run tab --apply again", message)
        self.assertIn("herdr tab close w1:t5", message)

        self.log.unlink()
        with self.assertRaises(herdr_tab.TabError) as caught:
            herdr_tab.apply(self.steps, self.env(FAKE_HERDR_FAIL="pane run"), say=self.said.append)
        self.assertIn("step 3 failed", str(caught.exception))
        self.assertIn("herdr tab close w1:t5", str(caught.exception))

    def test_an_agent_that_is_not_installed_stops_before_step_1(self) -> None:
        env = self.env()
        env["PATH"] = str(Path(self.tmp.name) / "empty")
        with self.assertRaisesRegex(herdr_tab.TabError, "'claude' is not installed"):
            herdr_tab.apply(self.steps, env, say=self.said.append)
        self.assertEqual(self.calls(), [])

    def test_a_reply_that_is_not_json_stops_the_steps(self) -> None:
        env = self.env(FAKE_HERDR_GARBLED="1")
        with self.assertRaisesRegex(herdr_tab.TabError, "step 2: herdr's reply is not JSON") as caught:
            herdr_tab.apply(self.steps, env, say=self.said.append)
        self.assertEqual(len(self.calls()), 2)
        self.assertIn("herdr tab close w1:t5", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
