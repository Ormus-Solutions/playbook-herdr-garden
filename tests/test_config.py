"""The config: what it accepts, and the message for each mistake."""
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import support  # first: it puts src/ on the path
from feedgarden import config


class ConfigTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def load(self, body: str) -> config.Config:
        return config.load(support.write_toml(self.dir, body))

    def refused(self, body: str) -> str:
        with self.assertRaises(config.ConfigError) as caught:
            self.load(body)
        return str(caught.exception)

    def test_the_example_configs_load(self) -> None:
        example = config.load(support.EXAMPLES / "config.example.toml")
        self.assertEqual(example.mode, "herdr")
        self.assertEqual(len(example.sources), 7)
        demo = config.load(support.DEMO)
        self.assertEqual(demo.sources[0].path, support.EXAMPLES / "sources" / "github-search.json")

    def test_a_minimal_config_gets_the_defaults(self) -> None:
        cfg = self.load(support.MINIMAL)
        self.assertEqual((cfg.mode, cfg.agent, cfg.max_age_days, cfg.per_kind), ("herdr", "garden", 30, 20))
        self.assertEqual(list(cfg.kinds), ["plugins", "skills", "repos", "news", "prompts", "coding"])
        self.assertEqual(cfg.board, config.DEFAULT_BOARD.expanduser())

    def test_a_missing_file_says_what_to_do(self) -> None:
        with self.assertRaises(config.ConfigError) as caught:
            config.load(self.dir / "nope.toml")
        self.assertIn("examples/config.example.toml", str(caught.exception))

    def test_the_config_is_found_by_flag_then_env_then_default(self) -> None:
        with mock.patch.dict(os.environ, {"GARDEN_CONFIG": "/tmp/from-env.toml"}):
            self.assertEqual(config.find_config("/tmp/flag.toml"), Path("/tmp/flag.toml"))
            self.assertEqual(config.find_config(None), Path("/tmp/from-env.toml"))
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(config.find_config(None).name, "config.toml")

    def test_mistakes_name_the_key(self) -> None:
        self.assertIn("'interests'", self.refused('[[sources]]\ntype = "rss"\nurl = "https://a.example"\n'))
        self.assertIn("[[sources]]", self.refused('interests = ["agent"]\n'))
        self.assertIn("'type'", self.refused('interests = ["a"]\n[[sources]]\ntype = "ftp"\n'))
        self.assertIn("https://", self.refused('interests = ["a"]\n[[sources]]\ntype = "rss"\nurl = "http://a"\n'))
        self.assertIn("owner/name", self.refused('interests = ["a"]\n[[sources]]\ntype = "github-releases"\n'))
        self.assertIn("'kind'", self.refused(support.MINIMAL + 'kind = "videos"\n'))
        self.assertIn("not valid TOML", self.refused("interests = [\n"))

    def test_handoff_settings_are_checked(self) -> None:
        self.assertIn("'mode'", self.refused(support.MINIMAL + '[handoff]\nmode = "email"\n'))
        self.assertIn("'agent'", self.refused(support.MINIMAL + '[handoff]\nagent = "Bad Name"\n'))
        self.assertIn("needs 'command'", self.refused(support.MINIMAL + '[handoff]\nmode = "command"\n'))
        cfg = self.load(support.MINIMAL + '[handoff]\nmode = "command"\ncommand = ["wl-copy"]\n')
        self.assertEqual(cfg.command, ["wl-copy"])

    def test_a_prompt_must_point_at_the_item(self) -> None:
        self.assertIn("{url}", self.refused(support.MINIMAL + '[prompts]\ndiff = "compare it"\n'))
        self.assertIn("one of", self.refused(support.MINIMAL + '[prompts]\ndelete = "{url}"\n'))

    def test_kinds_can_change_and_grow(self) -> None:
        cfg = self.load(support.MINIMAL + '[kinds.coding]\nwords = ["dotfiles"]\n'
                        '[kinds.mcp]\ntitle = "MCP servers"\nwords = ["MCP"]\n')
        self.assertEqual(cfg.kinds["coding"]["words"], ["dotfiles"])
        self.assertEqual(cfg.kinds["coding"]["title"], "How others code")
        self.assertEqual(cfg.kinds["mcp"], {"title": "MCP servers", "badge": "MCP", "words": ["mcp"]})
        self.assertEqual(list(cfg.kinds)[-1], "mcp")

    def test_paths_are_relative_to_the_config_file(self) -> None:
        cfg = self.load('interests = ["a"]\nboard = "state/board.json"\n'
                        '[[sources]]\ntype = "rss"\npath = "feeds/news.rss"\n')
        self.assertEqual(cfg.board, self.dir.resolve() / "state" / "board.json")
        self.assertEqual(cfg.sources[0].path, self.dir.resolve() / "feeds" / "news.rss")


if __name__ == "__main__":
    unittest.main()
