"""Shared helpers for the tests: the paths, the demo config and the demo board.

Every test runs offline, on the synthetic data in examples/. No test calls
the network, and no test calls the real `herdr`: the Herdr tests use a fake
one (fake_herdr below) that only writes down what it was asked.
"""
from __future__ import annotations

import os
import stat
import sys
import textwrap
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"
sys.path.insert(0, str(ROOT / "src"))

from feedgarden import config, kinds, sources  # imported after sys.path names src/

DEMO = EXAMPLES / "demo.toml"
TODAY = "2026-01-15"


def demo_config(**changes: Any) -> config.Config:
    return replace(config.load(DEMO), **changes)


def demo_board(cfg: config.Config | None = None) -> dict[str, Any]:
    cfg = cfg or demo_config()
    items, report = sources.collect(cfg, TODAY)
    return kinds.build_board(items, report, cfg, TODAY)


def item(**fields: Any) -> dict[str, Any]:
    """A made-up item with every field a stage reads; pass the ones a test cares about."""
    base: dict[str, Any] = {"key": "acme/demo", "title": "acme/demo", "url": "https://github.com/acme/demo",
                            "summary": "", "date": TODAY, "source": "test", "hint": ""}
    return base | fields


def write_toml(folder: Path, body: str) -> Path:
    path = folder / "config.toml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


MINIMAL = """
    interests = ["agent"]
    [[sources]]
    type = "rss"
    url = "https://news.example.com/feed.xml"
"""


FAKE_HERDR = r'''#!/usr/bin/env python3
"""A stand-in for herdr: it appends its arguments to a log and answers like the real CLI."""
import json, os, sys
args = sys.argv[1:]
with open(os.environ["FAKE_HERDR_LOG"], "a", encoding="utf-8") as f:
    f.write(json.dumps(args) + "\n")
fail = os.environ.get("FAKE_HERDR_FAIL", "")
if fail and " ".join(args[:2]) == fail:
    print(json.dumps({"error": {"code": "agent_not_ready", "message": "the pane is not at a prompt"}}),
          file=sys.stderr)
    sys.exit(1)
if os.environ.get("FAKE_HERDR_GARBLED") and args[:2] == ["pane", "split"]:
    print("{not json")
elif args[:2] == ["tab", "create"]:
    print(json.dumps({"result": {"type": "tab_created", "tab": {"tab_id": "w1:t5"},
                                 "root_pane": {"pane_id": "w1:p9"}}}))
elif args[:2] == ["pane", "split"]:
    print(json.dumps({"result": {"type": "pane_split", "pane": {"pane_id": "w1:p10"}}}))
elif args[:2] == ["agent", "prompt"] and os.environ.get("FAKE_HERDR_BLOCKED"):
    print(json.dumps({"error": {"code": "agent_blocked", "message": "waiting on a dialog"}}), file=sys.stderr)
    sys.exit(1)
else:
    print(json.dumps({"result": {"type": "ok"}}))
'''


def fake_herdr(folder: Path) -> tuple[Path, Path]:
    """Write the stand-in herdr into `folder`. Returns (program, log)."""
    program = folder / "herdr"
    program.write_text(FAKE_HERDR, encoding="utf-8")
    program.chmod(program.stat().st_mode | stat.S_IXUSR)
    return program, folder / "herdr.log"


def herdr_env(log: Path, **extra: str) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("FAKE_HERDR")}
    return env | {"HERDR_ENV": "1", "FAKE_HERDR_LOG": str(log)} | extra
