"""The text helpers: cleaning untrusted feed text, keys, and small formats."""
from __future__ import annotations

import unittest

import support  # first: it puts src/ on the path
from feedgarden import text


class CleanTest(unittest.TestCase):
    def test_tags_and_entities_become_plain_text(self) -> None:
        self.assertEqual(text.clean("<p>A <b>bold</b> &amp; plain</p>"), "A bold & plain")

    def test_terminal_escape_codes_are_removed(self) -> None:
        # An escape code in a title could recolour or move the cursor in your terminal.
        self.assertEqual(text.clean("red\x1b[31mtext\x1b[0m"), "redtext")
        self.assertNotIn("\x1b", text.clean("&#27;[2Jcleared"))  # an escape written as an entity
        self.assertEqual(text.clean("title\x1b]0;new window name\x07 end"), "title end")

    def test_newlines_and_control_characters_become_one_space(self) -> None:
        # A newline in a title must not start a new line in an agent prompt.
        self.assertEqual(text.clean("line one\n\nline two\r\x00\x07!"), "line one line two !")

    def test_long_text_is_cut_with_an_ellipsis(self) -> None:
        self.assertEqual(text.clean("abcdefghij", 5), "abcd…")

    def test_none_is_empty(self) -> None:
        self.assertEqual(text.clean(None), "")


class KeyTest(unittest.TestCase):
    def test_a_github_repo_url_gives_owner_and_name(self) -> None:
        self.assertEqual(text.key_for("https://github.com/acme/demo-api"), "acme/demo-api")
        self.assertEqual(text.key_for("https://github.com/acme/demo-api/"), "acme/demo-api")

    def test_any_other_url_gives_a_stable_link_key(self) -> None:
        key = text.key_for("https://news.example.com/a")
        self.assertRegex(key, r"^link/[0-9a-f]{12}$")
        self.assertEqual(key, text.key_for("https://news.example.com/a"))
        self.assertNotEqual(key, text.key_for("https://github.com/acme/demo-api/releases/tag/v1"))

    def test_key_ok_is_an_allow_list(self) -> None:
        self.assertTrue(text.key_ok("acme/demo-api"))
        self.assertTrue(text.key_ok("link/0123456789ab"))
        for bad in ("acme", "acme/demo api", "a/b/c", "acme/demo;rm", "acme/demo\n", ""):
            self.assertFalse(text.key_ok(bad), bad)

    def test_url_ok_wants_https_and_no_spaces(self) -> None:
        self.assertTrue(text.url_ok("https://news.example.com/a?b=1"))
        for bad in ("http://news.example.com/a", "javascript:alert(1)", "file:///etc/passwd",
                    "https://a b", "https://a\x1b"):
            self.assertFalse(text.url_ok(bad), bad)


class SmallFormatsTest(unittest.TestCase):
    def test_starts_word_matches_stems_at_word_start(self) -> None:
        self.assertTrue(text.starts_word("agent", "Run agents in panes"))
        self.assertTrue(text.starts_word("agent", "agent-skills"))
        self.assertTrue(text.starts_word("agents.md", "Set up AGENTS.md"))
        self.assertFalse(text.starts_word("agent", "a reagent"))

    def test_short_number(self) -> None:
        self.assertEqual([text.short_number(n) for n in (86, 1000, 1240, 1_300_000)],
                         ["86", "1k", "1.2k", "1.3M"])

    def test_wrap_breaks_on_spaces_and_cuts_long_words(self) -> None:
        self.assertEqual(text.wrap("one two three", 7), ["one two", "three"])
        self.assertEqual(text.wrap("abcdefghij", 4), ["abcd", "efgh", "ij"])


if __name__ == "__main__":
    unittest.main()
