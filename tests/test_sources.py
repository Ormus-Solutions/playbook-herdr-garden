"""The parsers and the collect step, on the synthetic feeds and on small made-up inputs."""
from __future__ import annotations

import os
import unittest
from typing import Any
from unittest import mock

import support  # first: it puts src/ on the path
from feedgarden import sources
from feedgarden.config import Source

RSS = (support.EXAMPLES / "sources" / "dev-news.rss").read_text(encoding="utf-8")
ATOM = (support.EXAMPLES / "sources" / "demo-api-releases.atom").read_text(encoding="utf-8")
SEARCH = (support.EXAMPLES / "sources" / "github-search.json").read_text(encoding="utf-8")


class ParseTest(unittest.TestCase):
    def test_rss_items_are_cleaned_and_dated(self) -> None:
        items = sources.parse_rss(RSS)
        self.assertEqual(len(items), 5)
        first = items[0]
        self.assertEqual(first["title"], "How we run five coding agents in one terminal")
        self.assertEqual(first["date"], "2026-01-13")
        self.assertEqual(first["summary"], "A team shows its Herdr layout: one tab per project, one pane per agent.")
        self.assertRegex(first["key"], r"^link/[0-9a-f]{12}$")

    def test_an_rss_link_to_a_repo_gets_the_repo_key(self) -> None:
        self.assertEqual(sources.parse_rss(RSS)[-1]["key"], "acme/tdd-skill")

    def test_atom_entries_use_the_alternate_link(self) -> None:
        items = sources.parse_atom(ATOM)
        self.assertEqual([i["title"] for i in items], ["v2.1.0", "v2.0.0"])
        self.assertEqual(items[0]["url"], "https://github.com/acme/demo-api/releases/tag/v2.1.0")
        self.assertEqual(items[0]["date"], "2026-01-13")
        self.assertEqual(items[0]["summary"], "Adds a streaming API for agents.")

    def test_github_search_keeps_stars_licence_topics_and_archived(self) -> None:
        items = {i["key"]: i for i in sources.parse_github_search(SEARCH)}
        self.assertEqual(len(items), 11)
        plugin = items["acme/review-plugin"]
        self.assertEqual((plugin["stars"], plugin["license"], plugin["date"]), (1240, "MIT", "2026-01-14"))
        self.assertEqual(plugin["topics"], ["agent-plugin", "code-review"])
        self.assertEqual(items["demo-org/review-prompts"]["license"], "")
        self.assertTrue(items["demo-org/old-agent-runner"]["archived"])

    def test_an_entry_without_a_web_link_is_left_out(self) -> None:
        rss = ("<rss><channel><item><title>no link</title></item>"
               "<item><title>bad</title><link>javascript:alert(1)</link></item>"
               "<item><title>plain</title><link>http://news.example.com/a</link></item></channel></rss>")
        self.assertEqual(sources.parse_rss(rss), [])

    def test_a_feed_with_entities_is_refused(self) -> None:
        bomb = '<?xml version="1.0"?><!DOCTYPE r [<!ENTITY a "aaaa">]><rss>&a;</rss>'
        with self.assertRaises(sources.SourceError):
            sources.parse_rss(bomb)

    def test_broken_input_is_a_source_error(self) -> None:
        with self.assertRaises(sources.SourceError):
            sources.parse_atom("<feed>")
        with self.assertRaises(sources.SourceError) as caught:
            sources.parse_github_search('{"message": "API rate limit exceeded"}')
        self.assertIn("rate limit", str(caught.exception))


class CollectTest(unittest.TestCase):
    def test_a_failing_source_is_reported_and_the_others_still_count(self) -> None:
        cfg = support.demo_config(sources=[
            Source(name="down", type="rss", url="https://news.example.com/down.xml"),
            Source(name="up", type="rss", url="https://news.example.com/up.xml"),
        ])

        def get(url: str, headers: dict[str, str]) -> str:
            if "down" in url:
                raise sources.SourceError("HTTP 503")
            return RSS

        items, report = sources.collect(cfg, support.TODAY, get)
        self.assertEqual(len(items), 5)
        self.assertEqual(report, [{"name": "down", "ok": False, "found": 0, "error": "HTTP 503"},
                                  {"name": "up", "ok": True, "found": 5}])

    def test_github_search_fills_since_and_sends_the_token_only_in_a_header(self) -> None:
        seen: dict[str, Any] = {}

        def get(url: str, headers: dict[str, str]) -> str:
            seen["url"], seen["headers"] = url, headers
            return SEARCH

        src = Source(name="s", type="github-search", query="topic:tui pushed:>{since}")
        with mock.patch.dict(os.environ, {"GITHUB_TOKEN": "test-value"}):
            sources.read_source(src, support.demo_config(), support.TODAY, get)
        self.assertIn("q=topic%3Atui+pushed%3A%3E2025-12-16", str(seen["url"]))
        self.assertNotIn("test-value", str(seen["url"]))
        self.assertEqual(seen["headers"]["Authorization"], "Bearer test-value")

    def test_a_release_title_gets_the_repo_name(self) -> None:
        src = Source(name="r", type="github-releases", repo="acme/demo-api", kind="news")
        items = sources.read_source(src, support.demo_config(), support.TODAY, lambda u, h: ATOM)
        self.assertEqual(items[0]["title"], "demo-api v2.1.0")
        self.assertTrue(items[0]["release"])
        self.assertEqual(items[0]["hint"], "news")


if __name__ == "__main__":
    unittest.main()
