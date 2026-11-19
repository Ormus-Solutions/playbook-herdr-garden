"""The Garden tab: the plan, and --apply against a stand-in herdr (never the real one)."""
from __future__ import annotations

import json
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

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text(encoding="utf-8").splitlines()]

    def test_each_id_comes_from_the_reply_before(self) -> None:
        ids = herdr_tab.apply(self.steps, support.herdr_env(self.log), say=self.said.append)
        self.assertEqual(ids, {"<picker-pane>": "w1:p9", "<tab>": "w1:t5", "<agent-pane>": "w1:p10"})
        calls = self.calls()
        self.assertEqual(calls[1][:3], ["pane", "split", "w1:p9"])
        self.assertEqual(calls[2][:3], ["pane", "run", "w1:p9"])
        self.assertEqual(calls[3], ["agent", "start", "garden", "--kind", "claude", "--pane", "w1:p10"])
        self.assertIn("To remove it: herdr tab close w1:t5", self.said)

    def test_it_refuses_outside_herdr_and_runs_nothing(self) -> None:
        env = support.herdr_env(self.log)
        del env["HERDR_ENV"]
        with self.assertRaisesRegex(herdr_tab.TabError, "HERDR_ENV"):
            herdr_tab.apply(self.steps, env, say=self.said.append)
        self.assertEqual(self.calls(), [])

    def test_it_stops_at_the_first_failed_step(self) -> None:
        env = support.herdr_env(self.log, FAKE_HERDR_FAIL="agent start")
        with self.assertRaisesRegex(herdr_tab.TabError, r"step 4 failed \(agent_not_ready\)"):
            herdr_tab.apply(self.steps, env, say=self.said.append)
        self.assertEqual(len(self.calls()), 4)

        self.log.unlink()
        env = support.herdr_env(self.log, FAKE_HERDR_FAIL="tab create")
        with self.assertRaisesRegex(herdr_tab.TabError, "step 1 failed"):
            herdr_tab.apply(self.steps, env, say=self.said.append)
        self.assertEqual(len(self.calls()), 1)  # nothing after the failed step ran


if __name__ == "__main__":
    unittest.main()
