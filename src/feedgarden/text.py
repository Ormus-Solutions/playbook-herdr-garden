"""Small text helpers used by every stage.

Feed text is untrusted: anyone can publish a repo name or an article title.
So it is cleaned once, where it enters (the pattern is called "validate at
the boundary"), and the rest of the code can trust what it holds:

- clean() removes HTML tags, control characters and terminal escape codes.
  An escape code in a title could move the cursor or change colours in your
  terminal, and a newline could start a new line in an agent prompt.
- key_ok() is an allow-list: a key is only letters, digits, dot, dash and
  underscore around one slash. Only keys that pass can name an item.
"""
from __future__ import annotations

import hashlib
import html
import re

_TAGS = re.compile(r"<[^>]{0,2000}>")
_ESCAPES = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?|\x1b.")
_SPACE = re.compile(r"\s+")
_KEY = re.compile(r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}")
_REPO_URL = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/?")


def clean(value: object, limit: int = 300) -> str:
    """Plain, single-line, printable text of at most `limit` characters."""
    text = "" if value is None else str(value)
    text = _TAGS.sub(" ", text)
    text = html.unescape(text)
    text = _ESCAPES.sub("", text)
    text = "".join(ch if ch.isprintable() else " " for ch in text)
    text = _SPACE.sub(" ", text).strip()
    if len(text) > limit:
        text = text[: max(limit - 1, 0)].rstrip() + "…"
    return text


def cut(text: str, width: int) -> str:
    """Fit text in `width` characters, with an ellipsis when it was cut."""
    if width <= 0:
        return ""
    return text if len(text) <= width else text[: width - 1] + "…"


def wrap(text: str, width: int) -> list[str]:
    """Break text into lines of at most `width` characters, on spaces."""
    lines: list[str] = []
    line = ""
    for word in text.split():
        while len(word) > width:  # a long URL: break it hard
            if line:
                lines.append(line)
                line = ""
            lines.append(word[:width])
            word = word[width:]
        if not line:
            line = word
        elif len(line) + 1 + len(word) <= width:
            line += " " + word
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    return lines


def key_ok(key: str) -> bool:
    return _KEY.fullmatch(key) is not None  # fullmatch: "$" would let a final newline through


def key_for(url: str) -> str:
    """The item's key: owner/repo for a GitHub repo, link/<12 hex> for anything else.

    One item found by two sources gets the same key, so it shows once.
    """
    m = _REPO_URL.fullmatch(url)
    if m:
        return f"{m.group(1)}/{m.group(2)}"
    return "link/" + hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def url_ok(url: str) -> bool:
    """Only https:// links reach a prompt. A plain http:// page can be changed on its way
    to the agent, and the agent is told to read it."""
    return url.startswith("https://") and not any(ch.isspace() for ch in url) \
        and all(ch.isprintable() for ch in url)


def starts_word(word: str, text: str) -> bool:
    """True when `word` starts a word in `text` (case does not matter).

    "agent" matches "agents" and "agent-tools", not "reagent". This is why the
    interests in the config can be short stems.
    """
    return re.search(r"(?<![a-z0-9])" + re.escape(word.lower()), text.lower()) is not None


def short_number(n: int) -> str:
    """1240 -> 1.2k, 1300000 -> 1.3M: the way the rows show stars."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(n)
