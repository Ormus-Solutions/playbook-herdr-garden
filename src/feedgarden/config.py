"""Read and check the config file (TOML).

Every setting lives in one file, so the code holds no hosts, user names or
paths. The file is found in this order: --config, then the GARDEN_CONFIG
environment variable, then ~/.config/playbook-herdr-garden/config.toml.

A wrong setting stops the tool with a message that names the key, before any
feed is fetched. This is called "fail fast": a typo shows at once, not as an
empty board later.
"""
from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from feedgarden.text import key_ok

DEFAULT_CONFIG = Path("~/.config/playbook-herdr-garden/config.toml")
DEFAULT_BOARD = Path("~/.local/state/playbook-herdr-garden/board.json")
SOURCE_TYPES = ("rss", "atom", "github-search", "github-releases")
HANDOFF_MODES = ("herdr", "command", "show")
ACTIONS = ("integrate", "diff", "analyze")
AGENT_NAME = re.compile(r"^[a-z][a-z0-9_-]{0,31}$")  # the names Herdr accepts for an agent

# The kinds, in the order the pane shows them. "words" decide the kind: the
# first kind with a word that starts a word of the item wins. A kind with no
# words is a fallback: a GitHub repo becomes "repos", anything else "news".
DEFAULT_KINDS: dict[str, dict[str, Any]] = {
    "plugins": {"title": "Plugins", "badge": "PLUGIN", "words": ["plugin", "marketplace", "extension"]},
    "skills": {"title": "Skills", "badge": "SKILL", "words": ["skill"]},
    "repos": {"title": "Repos", "badge": "REPO", "words": []},
    "news": {"title": "News", "badge": "NEWS", "words": []},
    "prompts": {"title": "Prompts", "badge": "PROMPT", "words": ["prompt"]},
    "coding": {"title": "How others code", "badge": "HOWTO",
               "words": ["agents.md", "claude.md", "dotfiles", "how we", "my setup", "our setup"]},
}


class ConfigError(SystemExit):
    """A setting is wrong; the message says which one and how to fix it."""


@dataclass(frozen=True)
class Source:
    name: str
    type: str
    url: str = ""
    path: Path | None = None  # a local file instead of the network (the demo uses this)
    query: str = ""
    repo: str = ""
    kind: str = ""


@dataclass(frozen=True)
class Config:
    path: Path
    title: str
    interests: list[str]
    sources: list[Source]
    kinds: dict[str, dict[str, Any]]
    board: Path
    setup: str = ""
    today: str = ""  # demo only: freeze the date so the output never changes
    max_age_days: int = 30
    min_stars: int = 0
    drop: list[str] = field(default_factory=list)
    per_kind: int = 20
    mode: str = "herdr"
    agent: str = "garden"
    command: list[str] = field(default_factory=list)
    herdr: str = "herdr"
    prompts: dict[str, str] = field(default_factory=dict)


def find_config(flag: str | None) -> Path:
    raw = flag or os.environ.get("GARDEN_CONFIG") or str(DEFAULT_CONFIG)
    return Path(raw).expanduser()


def _words(value: Any, key: str, name: str, empty_ok: bool = True) -> list[str]:
    if value is None:
        value = []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ConfigError(f"config {name}: '{key}' must be a list of words")
    if not value and not empty_ok:
        raise ConfigError(f"config {name}: '{key}' needs at least one word")
    return [v.strip().lower() for v in value]


def _int(table: dict[str, Any], key: str, default: int, name: str) -> int:
    value = table.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ConfigError(f"config {name}: '{key}' must be a whole number, 0 or more")
    return value


def _local(base: Path, raw: Any, key: str, name: str) -> Path:
    if not isinstance(raw, str) or not raw:
        raise ConfigError(f"config {name}: '{key}' must be a path")
    path = Path(raw).expanduser()
    return path if path.is_absolute() else base / path


def _kinds(raw: Any, name: str) -> dict[str, dict[str, Any]]:
    kinds = {k: dict(v) for k, v in DEFAULT_KINDS.items()}
    if raw is None:
        return kinds
    if not isinstance(raw, dict):
        raise ConfigError(f"config {name}: [kinds] must be tables like [kinds.skills]")
    for kind, table in raw.items():
        if not re.match(r"^[a-z][a-z0-9-]{0,30}$", kind) or not isinstance(table, dict):
            raise ConfigError(f"config {name}: [kinds.{kind}] needs a short lowercase name and keys")
        merged = kinds.get(kind, {"title": kind.title(), "badge": kind.upper()[:6], "words": []})
        for key in ("title", "badge"):
            if key in table:
                if not isinstance(table[key], str) or not table[key].strip():
                    raise ConfigError(f"config {name}: [kinds.{kind}] '{key}' must be text")
                merged[key] = table[key].strip()
        if "words" in table:
            merged["words"] = _words(table["words"], f"kinds.{kind}.words", name)
        kinds[kind] = merged
    return kinds


def _source(raw: Any, base: Path, kinds: dict[str, Any], n: int, name: str) -> Source:
    where = f"config {name}: source {n}"
    if not isinstance(raw, dict):
        raise ConfigError(f"{where} must be a [[sources]] table")
    stype = raw.get("type")
    if stype not in SOURCE_TYPES:
        raise ConfigError(f"{where}: 'type' must be one of {', '.join(SOURCE_TYPES)}")
    kind = raw.get("kind", "")
    if kind and kind not in kinds:
        raise ConfigError(f"{where}: 'kind' must be one of {', '.join(kinds)}")
    path = _local(base, raw["path"], "path", name) if "path" in raw else None
    url, query, repo = raw.get("url", ""), raw.get("query", ""), raw.get("repo", "")
    if stype in ("rss", "atom") and not (url or path):
        raise ConfigError(f"{where}: an {stype} source needs 'url' (or 'path' for a local file)")
    if url and not str(url).startswith("https://"):
        raise ConfigError(f"{where}: 'url' must start with https://")
    if stype == "github-search" and not (query or path):
        raise ConfigError(f"{where}: a github-search source needs 'query'")
    if stype == "github-releases" and not key_ok(str(repo)):
        raise ConfigError(f"{where}: a github-releases source needs 'repo' as owner/name")
    label = raw.get("name") or query or repo or url or (path.name if path else f"source {n}")
    return Source(name=str(label), type=stype, url=str(url), path=path, query=str(query),
                  repo=str(repo), kind=str(kind))


def load(path: Path) -> Config:
    """Read the TOML file at `path` and check every key the tool uses."""
    name = path.name
    if not path.is_file():
        raise ConfigError(f"no config at {path}: copy examples/config.example.toml there "
                          "and change it, or pass --config")
    try:
        with path.open("rb") as f:
            raw = tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"config {name} is not valid TOML: {e}") from None
    base = path.resolve().parent
    kinds = _kinds(raw.get("kinds"), name)
    sources = raw.get("sources") or []
    if not isinstance(sources, list) or not sources:
        raise ConfigError(f"config {name}: add at least one [[sources]] table")
    filt = raw.get("filter") or {}
    hand = raw.get("handoff") or {}
    prompts = raw.get("prompts") or {}
    if not isinstance(filt, dict) or not isinstance(hand, dict) or not isinstance(prompts, dict):
        raise ConfigError(f"config {name}: [filter], [handoff] and [prompts] must be tables")

    mode = hand.get("mode", "herdr")
    if mode not in HANDOFF_MODES:
        raise ConfigError(f"config {name}: [handoff] 'mode' must be one of {', '.join(HANDOFF_MODES)}")
    agent = hand.get("agent", "garden")
    if not isinstance(agent, str) or not AGENT_NAME.match(agent):
        raise ConfigError(f"config {name}: [handoff] 'agent' must be lowercase letters, digits, - or _ "
                          "(the names Herdr accepts)")
    command = hand.get("command", [])
    if not isinstance(command, list) or not all(isinstance(c, str) and c for c in command):
        raise ConfigError(f"config {name}: [handoff] 'command' must be a list like [\"wl-copy\"]")
    if mode == "command" and not command:
        raise ConfigError(f"config {name}: [handoff] mode \"command\" needs 'command'")
    for action, template in prompts.items():
        if action not in ACTIONS or not isinstance(template, str) or "{url}" not in template:
            raise ConfigError(f"config {name}: [prompts] '{action}' must be one of "
                              f"{', '.join(ACTIONS)}, as text that holds {{url}}")
    today = raw.get("today", "")
    if today and not re.match(r"^\d{4}-\d{2}-\d{2}$", str(today)):
        raise ConfigError(f"config {name}: 'today' must look like 2026-01-15")

    return Config(
        path=path,
        title=str(raw.get("title") or "garden"),
        interests=_words(raw.get("interests"), "interests", name, empty_ok=False),
        sources=[_source(s, base, kinds, n, name) for n, s in enumerate(sources, 1)],
        kinds=kinds,
        board=_local(base, raw["board"], "board", name) if "board" in raw else DEFAULT_BOARD.expanduser(),
        setup=str(raw.get("setup") or ""),
        today=str(today),
        max_age_days=_int(filt, "max_age_days", 30, name),
        min_stars=_int(filt, "min_stars", 0, name),
        drop=_words(filt.get("drop"), "filter.drop", name),
        per_kind=_int(filt, "per_kind", 20, name),
        mode=mode,
        agent=agent,
        command=list(command),
        herdr=str(hand.get("herdr") or "herdr"),
        prompts=dict(prompts),
    )
