#!/usr/bin/env python3
"""The Garden: a curated feed your agents can act on.

Usage:
    python3 src/garden.py --demo                      the board, from the synthetic feeds in examples/
    python3 src/garden.py --demo pick                 the pane, on the same board (nothing is sent)
    python3 src/garden.py collect                     read your sources, write the board file
    python3 src/garden.py board                       print the board file as text
    python3 src/garden.py pick                        the pane: i integrate, d diff, a analyze
    python3 src/garden.py prompt diff owner/repo      print the prompt a key would send
    python3 src/garden.py send diff owner/repo        hand it over, as [handoff] in the config says
    python3 src/garden.py tab                         print the Herdr commands for the Garden tab
    python3 src/garden.py tab --apply                 run them (inside a Herdr pane)
    python3 src/garden.py cron                        print the crontab line for a morning collect

Settings: --config, else $GARDEN_CONFIG, else ~/.config/playbook-herdr-garden/config.toml.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

from feedgarden import config as config_mod
from feedgarden import herdr_tab, kinds, pane, render, sources
from feedgarden.config import ACTIONS, Config
from feedgarden.handoff import HandoffError, build_prompt, send

ROOT = Path(__file__).resolve().parents[1]
DEMO_CONFIG = ROOT / "examples" / "demo.toml"


def today_of(cfg: Config, flag: str | None) -> str:
    return flag or cfg.today or dt.date.today().isoformat()


def empty_board(cfg: Config, today: str) -> dict[str, Any]:
    return kinds.build_board([], [], cfg, today)


def read_board(cfg: Config, today: str, demo: bool) -> dict[str, Any]:
    """The demo builds its board from the example feeds in memory; otherwise read the board file."""
    if demo:
        items, report = sources.collect(cfg, today)
        return kinds.build_board(items, report, cfg, today)
    try:
        return json.loads(cfg.board.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"no board yet at {cfg.board}: run python3 src/garden.py collect") from None
    except ValueError:
        raise SystemExit(f"the board file {cfg.board} is not valid JSON: run collect again") from None


def write_board(board: dict[str, Any], path: Path) -> None:
    """Write to a new file, then rename it over the old one. A rename is atomic, so the pane
    never reads half a board (the pattern is called an atomic write)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def find_item(board: dict[str, Any], key: str) -> dict[str, Any]:
    for item in [*board["items"], *board["skipped"]]:
        if item["key"].lower() == key.lower():
            return item
    raise SystemExit(f"no item {key} on the board: see the keys with python3 src/garden.py board")


def cmd_collect(cfg: Config, today: str, demo: bool) -> int:
    items, report = sources.collect(cfg, today)
    board = kinds.build_board(items, report, cfg, today)
    for s in report:
        state = f"{s['found']} items" if s["ok"] else f"FAILED: {s['error']}"
        print(f"{s['name']}: {state}")
    print(f"board: {len(board['items'])} kept, {len(board['skipped'])} skipped")
    if demo:
        print("demo: nothing written")
    else:
        write_board(board, cfg.board)
        print(f"written to {cfg.board}")
    return 1 if report and not any(s["ok"] for s in report) else 0


def cmd_pick(cfg: Config, today: str, demo: bool) -> int:
    if demo:
        board = read_board(cfg, today, demo=True)
        return pane.supervise(cfg, load=lambda: board, stamp=lambda: 0.0)

    def load() -> dict[str, Any]:
        try:
            return read_board(cfg, today, demo=False)
        except SystemExit as e:
            board = empty_board(cfg, today)
            board["title"] = f"{cfg.title} · {e}"
            return board

    def stamp() -> float:
        try:
            return cfg.board.stat().st_mtime
        except OSError:
            return 0.0

    return pane.supervise(cfg, load, stamp)


def cron_line(root: Path, python: str, config: Path) -> str:
    """The crontab line for a collect at 07:20 every morning.

    cron runs the command with /bin/sh, a short PATH (often /usr/bin:/bin) and no
    profile. So every path is absolute and in single quotes, and the interpreter
    is the one running now (3.11 or newer), not whatever python3 cron finds. A '
    cannot sit inside single quotes, and cron reads % as a new line, so a path
    with either is refused instead of written as a line that fails every morning.
    """
    for path in (str(root), python, str(config)):
        if "'" in path or "%" in path:
            raise SystemExit(f"cron cannot run from {path}: the path holds ' or %. Move it, then try again")
    return (f"20 7 * * * cd '{root}' && '{python}' src/garden.py --config '{config}' collect "
            ">> ~/.local/state/playbook-herdr-garden/collect.log 2>&1")


def cmd_tab(cfg: Config, args: argparse.Namespace, demo: bool) -> int:
    steps = herdr_tab.plan(cfg.herdr, ROOT, cfg.path.resolve(), cfg.agent, args.kind, args.label,
                           os.environ.get("HERDR_WORKSPACE_ID", ""))
    if not args.apply:
        sys.stdout.write(herdr_tab.plan_text(steps))
        return 0
    if demo:
        raise SystemExit("the demo never changes Herdr: use your own config for tab --apply")
    try:
        herdr_tab.apply(steps, os.environ)
    except herdr_tab.TabError as e:
        print(f"tab: {e}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="The Garden: a curated feed your agents can act on.")
    parser.add_argument("--config", help="the config file (default: $GARDEN_CONFIG, then "
                        f"{config_mod.DEFAULT_CONFIG})")
    parser.add_argument("--demo", action="store_true", help="use the synthetic feeds in examples/")
    parser.add_argument("--today", help="the date to judge age against, like 2026-01-15")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("board", help="print the board as text (the default)")
    sub.add_parser("collect", help="read the sources and write the board file")
    sub.add_parser("pick", help="open the pane")
    for name, what in (("prompt", "print the prompt for one item"), ("send", "hand that prompt over")):
        p = sub.add_parser(name, help=what)
        p.add_argument("action", choices=ACTIONS)
        p.add_argument("key", help="the item's key, as the board shows it")
    t = sub.add_parser("tab", help="the Herdr commands that build the Garden tab")
    t.add_argument("--apply", action="store_true", help="run them (inside a Herdr pane)")
    t.add_argument("--kind", default="claude", help="the agent Herdr starts (claude, codex, grok, ...)")
    t.add_argument("--label", default="Garden", help="the tab's name")
    sub.add_parser("cron", help="print the crontab line for a morning collect")
    args = parser.parse_args(argv)

    if args.today:
        try:
            dt.date.fromisoformat(args.today)
        except ValueError:
            parser.error("--today must look like 2026-01-15")
    cfg = config_mod.load(DEMO_CONFIG if args.demo else config_mod.find_config(args.config))
    today = today_of(cfg, args.today)
    command = args.command or "board"

    if command == "collect":
        return cmd_collect(cfg, today, args.demo)
    if command == "pick":
        return cmd_pick(cfg, today, args.demo)
    if command == "tab":
        return cmd_tab(cfg, args, args.demo)
    if command == "cron":
        print(cron_line(ROOT, sys.executable, cfg.path.resolve()))
        return 0
    board = read_board(cfg, today, args.demo)
    if command == "board":
        sys.stdout.write(render.board_text(board))
        return 0
    item = find_item(board, args.key)
    try:
        prompt = build_prompt(args.action, item, cfg)
        if command == "prompt":
            print(prompt)
            return 0
        if cfg.mode == "show":
            print(prompt)
        print(send(prompt, cfg), file=sys.stderr)
    except HandoffError as e:
        print(f"{command}: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
