"""The filter: which kind an item is, whether it stays, its fit, and the board."""
from __future__ import annotations

import unittest

import support  # first: it puts src/ on the path
from feedgarden import kinds
from feedgarden.config import DEFAULT_KINDS

item = support.item


class ClassifyTest(unittest.TestCase):
    def test_the_source_hint_wins(self) -> None:
        self.assertEqual(kinds.classify(item(title="a plugin", hint="news"), DEFAULT_KINDS), "news")

    def test_the_first_kind_with_a_matching_word_wins(self) -> None:
        cases = {
            "A plugin for agents": "plugins",
            "An agent skill (SKILL.md)": "skills",
            "System prompts for review": "prompts",
            "How we set up AGENTS.md": "coding",
        }
        for title, kind in cases.items():
            self.assertEqual(kinds.classify(item(title=title), DEFAULT_KINDS), kind, title)

    def test_with_no_word_a_repo_is_a_repo_and_a_link_is_news(self) -> None:
        self.assertEqual(kinds.classify(item(title="a tool", stars=5), DEFAULT_KINDS), "repos")
        self.assertEqual(kinds.classify(item(title="a post"), DEFAULT_KINDS), "news")

    def test_topics_count_as_words(self) -> None:
        self.assertEqual(kinds.classify(item(title="x", topics=["claude-code-plugin"], stars=1),
                                        DEFAULT_KINDS), "plugins")
        self.assertEqual(kinds.classify(item(title="x", topics=["agent-skills"], stars=1),
                                        DEFAULT_KINDS), "skills")


class JudgeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.cfg = support.demo_config()

    def judge(self, **fields: object) -> dict[str, object]:
        return kinds.judge(item(**fields), self.cfg, support.TODAY)

    def test_each_skip_rule_names_itself(self) -> None:
        self.assertEqual(self.judge(title="airdrop agent")["reason"], 'has the drop word "airdrop"')
        self.assertIn("archived", str(self.judge(title="agent", archived=True)["reason"]))
        self.assertEqual(self.judge(title="agent", date="2025-12-01")["reason"], "older than 30 days")
        self.assertEqual(self.judge(title="agent", stars=4)["reason"], "under 5 stars")
        self.assertEqual(self.judge(title="a cake recipe")["reason"], "matches none of your interests")

    def test_an_item_with_no_date_is_not_too_old(self) -> None:
        self.assertNotIn("reason", self.judge(title="agent", date=""))

    def test_fit_counts_interests_stars_and_freshness(self) -> None:
        plain = self.judge(title="agent", date="2026-01-01")
        self.assertEqual((plain["fit"], plain["why"], plain["group"]), (1, ["matches agent"], "agent"))
        full = self.judge(title="terminal agent test api python", stars=1500, date="2026-01-14")
        self.assertEqual(full["fit"], 5)  # 5 interests + stars + fresh, capped at 5
        self.assertEqual(full["why"], ["matches agent, terminal, test, python, api", "1.5k stars", "fresh"])
        self.assertEqual(full["group"], "agent")  # the first interest in the config's order


class BoardTest(unittest.TestCase):
    def test_the_demo_board(self) -> None:
        board = support.demo_board()
        kept = {i["key"]: i["kind"] for i in board["items"]}
        self.assertEqual(kept["acme/review-plugin"], "plugins")
        self.assertEqual(kept["acme/tdd-skill"], "skills")
        self.assertEqual(kept["demo-org/pane-notes"], "repos")
        self.assertEqual(kept["demo-org/review-prompts"], "prompts")
        self.assertEqual(kept["acme/agent-dotfiles"], "coding")
        self.assertEqual(len(board["items"]), 10)
        self.assertEqual(len(board["skipped"]), 7)
        self.assertTrue(all(s["ok"] for s in board["sources"]))

    def test_an_item_found_twice_shows_once(self) -> None:
        keys = [i["key"] for i in support.demo_board()["items"]]
        self.assertEqual(keys.count("acme/tdd-skill"), 1)

    def test_each_kind_keeps_its_best_and_skips_the_rest(self) -> None:
        cfg = support.demo_config(per_kind=1)
        rows = [item(key=f"acme/r{n}", title=f"agent r{n}", stars=10 * n, hint="repos") for n in (1, 2, 3)]
        board = kinds.build_board(rows, [], cfg, support.TODAY)
        self.assertEqual([i["key"] for i in board["items"]], ["acme/r3"])
        self.assertEqual({s["key"]: s["reason"] for s in board["skipped"]},
                         {"acme/r1": "past the 1 best of its kind", "acme/r2": "past the 1 best of its kind"})
        self.assertNotIn("fit", board["skipped"][0])

    def test_rows_are_grouped_by_interest_in_the_config_order(self) -> None:
        cfg = support.demo_config()
        rows = [item(key="acme/t", title="terminal tool", hint="repos", stars=900),
                item(key="acme/a", title="agent tool", hint="repos", stars=10)]
        board = kinds.build_board(rows, [], cfg, support.TODAY)
        self.assertEqual([i["key"] for i in board["items"]], ["acme/a", "acme/t"])


if __name__ == "__main__":
    unittest.main()
