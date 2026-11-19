"""The Herdr commands that build the Garden tab: the pane on the left, an agent on the right.

    +---------------------------+---------------------------+
    | picker pane               | agent pane                |
    | python3 src/garden.py pick| claude (or codex, grok)   |
    |  keys i, d, a  ---------> |  gets the prompt          |
    +---------------------------+---------------------------+

Four public Herdr commands do it (see `herdr --skill`):
    herdr tab create   a new tab; its reply names the tab and its first pane
    herdr pane split   a second pane to the right; its reply names the new pane
    herdr pane run     types the picker command into the first pane's shell
    herdr agent start  starts the agent in the second pane, under a name

By default the tool only prints the commands, so you can read them first.
This is a "dry run": you see every change before it happens. With --apply
it runs them, and takes each id from the JSON reply of the step before.
"""
from __future__ import annotations

import json
import shlex
import shutil
import subprocess
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from feedgarden.handoff import herdr_error

Run = Callable[..., subprocess.CompletedProcess[str]]
PICKER, AGENT, TAB = "<picker-pane>", "<agent-pane>", "<tab>"


class TabError(Exception):
    """A step failed; the message names the step and herdr's answer, `code` is herdr's error code."""

    def __init__(self, message: str, code: str = "") -> None:
        super().__init__(message)
        self.code = code


def picker_command(config: Path) -> str:
    """What the picker pane runs. It is typed into that pane's shell, so it is quoted for a shell."""
    return f"python3 src/garden.py --config {shlex.quote(str(config))} pick"


def plan(herdr: str, repo: Path, config: Path, agent: str, kind: str, label: str,
         workspace: str = "") -> list[list[str]]:
    """The four commands, with placeholders where an id from an earlier reply goes."""
    where = ["--workspace", workspace] if workspace else []
    return [
        [herdr, "tab", "create", *where, "--label", label, "--cwd", str(repo), "--no-focus"],
        [herdr, "pane", "split", PICKER, "--direction", "right", "--cwd", str(repo), "--no-focus"],
        [herdr, "pane", "run", PICKER, picker_command(config)],
        [herdr, "agent", "start", agent, "--kind", kind, "--pane", AGENT],
    ]


NOTES = [
    "#   picker pane: .result.root_pane.pane_id   tab: .result.tab.tab_id",
    "#   agent pane: .result.pane.pane_id",
    "",
    "",
]


def plan_text(steps: list[list[str]]) -> str:
    out = ["# Build the Garden tab. Run these inside a Herdr pane, in this order.",
           "# Each one prints JSON; the next one needs an id from it."]
    for argv, note in zip(steps, NOTES):
        out.append(shlex.join(argv))
        if note:
            out.append(note)
    out.append("# Or let the tool run them and fill in the ids: python3 src/garden.py tab --apply")
    return "\n".join(out) + "\n"


def _get(reply: Any, *path: str) -> str:
    node = reply
    for part in path:
        node = node.get(part) if isinstance(node, dict) else None
    if not isinstance(node, str) or not node:
        raise TabError(f"herdr's reply has no {'.'.join(path)}")
    return node


def _left_over(tab: str, agent: str, code: str) -> str:
    """What to do about a tab that step 1 made before a later step failed.

    Running tab --apply again would make a second tab, and the agent's name
    would still be taken, so the message names the tab and the way out.
    """
    close = f"herdr tab close {tab}"
    if code == "agent_not_ready":
        return (f"The tab {tab} is built, and the agent may wait on a first-run question in the right "
                f"pane (folder trust, sign-in). Answer it there, then check: herdr agent wait {agent} "
                f"--until idle --timeout 60000. Do not run tab --apply again. To start over instead: "
                f"{close}")
    return f"The tab {tab} was made and is left as it is. Remove it before you try again: {close}"


def apply(steps: list[list[str]], env: Mapping[str, str], run: Run = subprocess.run,
          say: Callable[[str], None] = print) -> dict[str, str]:
    """Run the steps in order and stop at the first one that fails. Returns the ids."""
    if env.get("HERDR_ENV") != "1":
        raise TabError("not inside a Herdr pane (HERDR_ENV is not 1): open a pane in Herdr and run "
                       "this there, or run the printed commands by hand")
    start = steps[-1]  # herdr agent start NAME --kind KIND --pane ...
    agent, kind = start[3], start[start.index("--kind") + 1]
    # Herdr's --kind is also the program's name, so a missing agent shows now, before
    # any tab exists, instead of as a failed step 4 in a half-built tab.
    if shutil.which(kind, path=env.get("PATH")) is None:
        raise TabError(f"the agent '{kind}' is not installed, or not on PATH (command -v {kind} finds "
                       "nothing). Install it, or name another with --kind. Nothing was changed")
    ids: dict[str, str] = {}
    try:
        _run_steps(steps, env, run, say, ids)
    except TabError as e:
        if TAB in ids:
            raise TabError(f"{e}\n{_left_over(ids[TAB], agent, e.code)}", e.code) from None
        raise
    say(f"The Garden tab is ready: tab {ids[TAB]}, picker pane {ids[PICKER]}, agent pane {ids[AGENT]}.")
    say(f"To open it: herdr tab focus {ids[TAB]} (or click it in the Herdr sidebar)")
    say(f"To remove it: herdr tab close {ids[TAB]}")
    return ids


def _run_steps(steps: list[list[str]], env: Mapping[str, str], run: Run, say: Callable[[str], None],
               ids: dict[str, str]) -> None:
    """Run each step and fill `ids` as the replies come, so a failure still knows the tab."""
    for n, step in enumerate(steps, 1):
        argv = [ids.get(part, part) for part in step]
        try:
            done = run(argv, capture_output=True, text=True, timeout=90, env=dict(env),
                       stdin=subprocess.DEVNULL)
        except FileNotFoundError:
            raise TabError(f"step {n}: {argv[0]} is not installed, or not on PATH") from None
        except subprocess.TimeoutExpired:
            raise TabError(f"step {n}: no answer in 90 s. Look at the tab before you run it again") from None
        if done.returncode != 0:
            code, message = herdr_error(done.stderr)
            raise TabError(f"step {n} failed ({code or 'exit ' + str(done.returncode)}): {message}. "
                           f"The command was: {shlex.join(argv)}", code)
        try:
            reply = json.loads(done.stdout) if done.stdout.strip() else {}
        except ValueError:
            raise TabError(f"step {n}: herdr's reply is not JSON. Look at the tab before you run it "
                           "again") from None
        if n == 1:
            ids[TAB] = _get(reply, "result", "tab", "tab_id")  # first: the tab exists from here on
            ids[PICKER] = _get(reply, "result", "root_pane", "pane_id")
        elif n == 2:
            ids[AGENT] = _get(reply, "result", "pane", "pane_id")
        say(f"step {n} ok: {shlex.join(argv[1:4])}")
