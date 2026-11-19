"""The pane's pure half: keys, the screen, and an action. No terminal is needed."""
from __future__ import annotations

import curses
import sys
import unittest

import support  # first: it puts src/ on the path
from feedgarden import kinds, pane, render
from feedgarden.sources import Item


def current(st: pane.State) -> Item:
    """The selected item; a test that reads one fails here when there is none."""
    item = st.current()
    assert item is not None, "no item is selected"
    return item


class KeysTest(unittest.TestCase):
    def setUp(self) -> None:
        self.st = pane.State(support.demo_board())

    def test_moving_stays_inside_the_list(self) -> None:
        self.assertEqual(current(self.st)["key"], "acme/review-plugin")
        pane.handle_key(self.st, curses.KEY_DOWN)
        pane.handle_key(self.st, ord("j"))  # only two plugins: the second key stops at the end
        self.assertEqual(current(self.st)["key"], "demo-org/pane-test-plugin")
        pane.handle_key(self.st, curses.KEY_UP)
        pane.handle_key(self.st, ord("k"))
        self.assertEqual(current(self.st)["key"], "acme/review-plugin")

    def test_kinds_switch_by_arrow_tab_and_number(self) -> None:
        pane.handle_key(self.st, curses.KEY_RIGHT)
        self.assertEqual(self.st.section, "skills")
        pane.handle_key(self.st, ord("\t"))
        self.assertEqual(self.st.section, "repos")
        pane.handle_key(self.st, ord("7"))
        self.assertEqual(self.st.section, render.SKIPPED)
        pane.handle_key(self.st, curses.KEY_RIGHT)  # past the last section: back to the first
        self.assertEqual(self.st.section, "plugins")
        pane.handle_key(self.st, ord("9"))  # there is no section 9: nothing changes
        self.assertEqual(self.st.section, "plugins")

    def test_each_kind_remembers_its_row(self) -> None:
        pane.handle_key(self.st, ord("j"))
        pane.handle_key(self.st, ord("2"))
        pane.handle_key(self.st, ord("1"))
        self.assertEqual(current(self.st)["key"], "demo-org/pane-test-plugin")

    def test_action_keys(self) -> None:
        self.assertEqual([pane.handle_key(self.st, ord(k)) for k in "idagq"],
                         ["integrate", "diff", "analyze", "reload", "quit"])


class ScreenTest(unittest.TestCase):
    def test_the_screen_fits_and_marks_the_selected_row(self) -> None:
        st = pane.State(support.demo_board())
        pane.handle_key(st, ord("4"))
        pane.handle_key(st, ord("j"))
        lines = pane.screen(st, 80, 24)
        self.assertEqual(len(lines), 24)
        selected = [render.text(line) for line, sel in lines if sel]
        self.assertEqual(len(selected), 1)
        self.assertIn("Testing agents: a field report", selected[0])
        self.assertIn("Why: matches agent, test · fresh", [render.text(line) for line, _ in lines])
        self.assertEqual(render.text(lines[-1][0]), render.KEYS)

    def test_a_long_list_scrolls_to_keep_the_row_in_view(self) -> None:
        cfg = support.demo_config()
        rows = [support.item(key=f"acme/r{n:02}", title=f"agent r{n:02}", hint="repos") for n in range(30)]
        st = pane.State(kinds.build_board(rows, [], cfg, support.TODAY))
        pane.handle_key(st, ord("3"))
        for _ in range(25):
            pane.handle_key(st, ord("j"))
        selected = [render.text(line) for line, sel in pane.screen(st, 80, 20) if sel]
        self.assertEqual(len(selected), 1)
        self.assertIn(current(st)["title"], selected[0])

    def test_an_empty_board_says_what_to_do(self) -> None:
        st = pane.State(kinds.build_board([], [], support.demo_config(), support.TODAY))
        texts = [render.text(line) for line, _ in pane.screen(st, 80, 20)]
        self.assertTrue(any("run collect" in t for t in texts))
        self.assertIsNone(st.current())


class ActTest(unittest.TestCase):
    def test_show_mode_puts_the_prompt_on_screen(self) -> None:
        st = pane.State(support.demo_board())
        pane.act(st, "diff", support.demo_config(mode="show"))
        self.assertIn("Garden pick, diff", st.shown)
        texts = [render.text(line) for line, _ in pane.screen(st, 80, 30)]
        self.assertIn("Prompt (not sent, copy it from here):", texts)
        pane.handle_key(st, ord("j"))
        self.assertEqual(st.shown, "")  # the next key goes back to the item

    def test_command_mode_reports_the_send(self) -> None:
        st = pane.State(support.demo_board())
        cfg = support.demo_config(mode="command", command=[sys.executable, "-c", "import sys; sys.stdin.read()"])
        pane.act(st, "analyze", cfg)
        self.assertTrue(st.message.startswith("analyze acme/review-plugin: sent to"))

    def test_a_failed_handoff_is_shown_not_raised(self) -> None:
        st = pane.State(support.demo_board())
        pane.act(st, "integrate", support.demo_config(mode="command", command=["/nonexistent/program"]))
        self.assertIn("not sent", st.message)


if __name__ == "__main__":
    unittest.main()
