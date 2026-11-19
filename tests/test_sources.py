"""The parsers and the collect step, on the synthetic feeds and on small made-up inputs."""
from __future__ import annotations

import http.server
import os
import threading
import unittest
import urllib.request
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


class RedirectTest(unittest.TestCase):
    """fetch() follows a redirect only to https://, and keeps the token on its own host."""

    def follow(self, old: str, new: str) -> urllib.request.Request | None:
        req = urllib.request.Request(old, headers={"Authorization": "Bearer test-value"})
        return sources.SafeRedirect().redirect_request(req, None, 302, "Found", {}, new)

    def test_a_redirect_that_leaves_https_is_refused(self) -> None:
        with self.assertRaises(sources.SourceError) as caught:
            self.follow("https://feeds.example.com/a", "http://feeds.example.com/a")
        self.assertIn("https://", str(caught.exception))

    def test_the_token_stays_on_its_own_host(self) -> None:
        same = self.follow("https://api.github.com/search", "https://api.github.com/search?page=2")
        other = self.follow("https://api.github.com/search", "https://elsewhere.example.com/")
        assert same is not None and other is not None
        self.assertEqual(same.get_header("Authorization"), "Bearer test-value")
        self.assertIsNone(other.get_header("Authorization"))

    def test_fetch_uses_it(self) -> None:
        # A real server on this machine's loopback address: it sends a redirect
        # to a plain http:// page, and fetch() must refuse to follow it.
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", "/plain")
                    self.end_headers()
                else:
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"followed")

            def log_message(self, *args: Any) -> None:
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        no_proxy = {k: "" for k in ("http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY")}
        with mock.patch.dict(os.environ, {**no_proxy, "no_proxy": "*"}):
            with self.assertRaises(sources.SourceError):
                sources.fetch(f"http://127.0.0.1:{server.server_port}/start", {})


if __name__ == "__main__":
    unittest.main()
