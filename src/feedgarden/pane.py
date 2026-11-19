"""The browsable pane (the "picker"): the board on screen, one key per action.

The pane has two halves, and only the second one touches the terminal:
- handle_key() and screen() are pure: a key and the state in, the new state
  and the lines to draw out. The tests drive them with no terminal at all.
- run() is the curses loop: read a key, call the pure half, draw the lines.

The pane runs under a "supervisor loop" (supervise()): when it crashes, it
prints the error and starts again after 3 seconds, so the pane in your Herdr
tab never turns into a bare shell. q quits for good; Ctrl+C stops the loop.
"""
from __future__ import annotations

import curses
import locale
import sys
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from feedgarden import render
from feedgarden.config import ACTIONS, Config
from feedgarden.handoff import HandoffError, build_prompt, describe, send
from feedgarden.render import Line
from feedgarden.sources import Item
from feedgarden.text import wrap

KEY_ACTIONS = {ord("i"): "integrate", ord("d"): "diff", ord("a"): "analyze"}
RESTART_AFTER = 3.0  # seconds: long enough that a crash loop cannot spin the CPU
TICK_MS = 2000  # the pane looks for a new board file this often


@dataclass
class State:
    board: dict[str, Any]
    sec: int = 0
    pos: dict[str, int] = field(default_factory=dict)
    top: dict[str, int] = field(default_factory=dict)
    message: str = ""
    shown: str = ""  # a prompt shown on screen (mode "show"), until the next key

    @property
    def section(self) -> str:
        return render.sections(self.board)[self.sec][0]

    def rows(self) -> list[Item]:
        return render.rows_of(self.board, self.section)

    def current(self) -> Item | None:
        rows = self.rows()
        if not rows:
            return None
        return rows[min(self.pos.get(self.section, 0), len(rows) - 1)]


def handle_key(st: State, key: int) -> str | None:
    """Apply one key. Returns "quit", "reload", an action name, or None."""
    count = len(render.sections(st.board))
    st.shown = ""
    if key in (ord("q"), 27):
        return "quit"
    if key == ord("g"):
        return "reload"
    if key in KEY_ACTIONS:
        return KEY_ACTIONS[key]
    rows = len(st.rows())
    here = st.pos.get(st.section, 0)
    if key in (curses.KEY_DOWN, ord("j")) and rows:
        st.pos[st.section] = min(here + 1, rows - 1)
    elif key in (curses.KEY_UP, ord("k")) and rows:
        st.pos[st.section] = max(here - 1, 0)
    elif key in (curses.KEY_RIGHT, ord("l"), ord("\t")):
        st.sec = (st.sec + 1) % count
    elif key in (curses.KEY_LEFT, ord("h"), curses.KEY_BTAB):
        st.sec = (st.sec - 1) % count
    elif ord("1") <= key <= ord("9") and key - ord("1") < count:
        st.sec = key - ord("1")
    return None


def screen(st: State, width: int, height: int) -> list[tuple[Line, bool]]:
    """Every line of the screen, top to bottom: (segments, selected)."""
    lines = render.section_lines(st.board, st.section)
    current = st.current()
    list_h = max(3, (height - 5) * 55 // 100)
    chosen = next((n for n, (_, it) in enumerate(lines) if it is current and it is not None), 0)
    top = st.top.get(st.section, 0)
    top = min(top, chosen) if chosen < top + list_h else chosen - list_h + 1
    st.top[st.section] = top

    out: list[tuple[Line, bool]] = [
        ([(render.header(st.board), "head")], False),
        (render.tabs(st.board, st.section), False),
    ]
    if not lines:
        out.append(([("  nothing here: run collect, or loosen the filter in your config", "dim")], False))
    for n, (line, item) in enumerate(lines[top: top + list_h], top):
        out.append((line, item is not None and n == chosen))
    out += [([("", "plain")], False)] * (2 + list_h - len(out))
    out.append(([("─" * width, "dim")], False))

    detail_h = height - len(out) - 2
    if st.shown:
        body: list[Line] = [[("Prompt (not sent, copy it from here):", "head")]]
        body += [[(t, "plain")] for t in wrap(st.shown, width)]
    elif current is not None:
        body = render.detail_lines(current, width)
    else:
        body = []
    out += [(line, False) for line in body[:max(detail_h, 0)]]
    out += [([("", "plain")], False)] * max(detail_h - len(body), 0)
    out.append(([(st.message, "warn")], False))
    out.append(([(render.KEYS, "dim")], False))
    return out[:height]


def act(st: State, action: str, cfg: Config, before_send: Callable[[], None] = lambda: None) -> None:
    """Build the prompt for the selected item and hand it over; the outcome goes to the status line."""
    item = st.current()
    if item is None:
        st.message = "no item here"
        return
    try:
        prompt = build_prompt(action, item, cfg)
        if cfg.mode == "show":
            st.shown = prompt
        else:
            st.message = f"{action}: sending to {describe(cfg)}…"
            before_send()
        st.message = f"{action} {item['key']}: " + send(prompt, cfg)
    except HandoffError as e:
        st.message = f"{action}: not sent: {e}"


# ---- the terminal half ----------------------------------------------------

STYLES = {"ok": 1, "warn": 2, "head": 3, "badge": 4, "dots": 5, "name": 0, "plain": 0, "dim": 0}


def _colours() -> dict[str, int]:
    attrs = {name: curses.A_NORMAL for name in STYLES}
    if curses.has_colors():
        curses.start_color()
        curses.use_default_colors()
        for n, colour in ((1, curses.COLOR_GREEN), (2, curses.COLOR_YELLOW), (3, curses.COLOR_CYAN),
                          (4, curses.COLOR_MAGENTA), (5, curses.COLOR_YELLOW)):
            curses.init_pair(n, colour, -1)
        attrs |= {name: curses.color_pair(n) for name, n in STYLES.items() if n}
    attrs["head"] |= curses.A_BOLD
    attrs["dim"] = curses.A_DIM
    attrs["sel"] = curses.A_REVERSE
    return attrs


def _draw(scr: Any, st: State, attrs: dict[str, int]) -> None:
    height, width = scr.getmaxyx()
    scr.erase()
    for y, (line, selected) in enumerate(screen(st, width, height)):
        x = 0
        for text, style in line:
            if x >= width - 1:
                break
            attr = attrs["sel"] if selected else attrs.get(style, curses.A_NORMAL)
            try:
                scr.addnstr(y, x, text, width - 1 - x, attr)
            except curses.error:
                pass  # the last cell of the screen cannot take a character
            x += len(text)
    scr.refresh()


def run(scr: Any, st: State, cfg: Config, load: Callable[[], dict[str, Any]],
        stamp: Callable[[], float]) -> None:
    curses.curs_set(0)
    attrs = _colours()
    scr.timeout(TICK_MS)
    seen = stamp()
    while True:
        _draw(scr, st, attrs)
        key = scr.getch()
        if key == -1:  # no key: look for a newer board (collect ran)
            if stamp() != seen:
                seen, st.board = stamp(), load()
                st.message = "a new board was loaded"
            continue
        event = handle_key(st, key)
        if event == "quit":
            return
        if event == "reload":
            seen, st.board = stamp(), load()
            st.message = "board loaded again"
        elif event in ACTIONS:
            act(st, event, cfg, before_send=lambda: _draw(scr, st, attrs))


def supervise(cfg: Config, load: Callable[[], dict[str, Any]], stamp: Callable[[], float]) -> int:
    locale.setlocale(locale.LC_ALL, "")  # so curses draws ● and ✓
    while True:
        try:
            curses.wrapper(run, State(load()), cfg, load, stamp)
            return 0
        except KeyboardInterrupt:
            return 130
        except Exception:  # any crash: show it, then start again (the supervisor's job)
            traceback.print_exc()
            print(f"the pane stopped; it starts again in {RESTART_AFTER:.0f} s (Ctrl+C stops it)",
                  file=sys.stderr)
            try:
                time.sleep(RESTART_AFTER)
            except KeyboardInterrupt:
                return 130
