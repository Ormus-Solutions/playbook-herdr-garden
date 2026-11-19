"""Draw the board as segments: (text, style) pairs.

The pane and the text preview use the same functions, so what the tests
check is what you see. The pane maps each style to a colour; the text
preview just joins the text. This split is called "separate the content
from the display": the content is easy to test, the display stays thin.
"""
from __future__ import annotations

from typing import Any

from feedgarden.sources import Item
from feedgarden.text import cut, short_number, wrap

Seg = tuple[str, str]
Line = list[Seg]
SKIPPED = "skipped"
KEYS = "↑↓ move · ←→ or 1-9 kind · i integrate · d diff · a analyze · g reload · q quit"
NAME_MAX = 34


def sections(board: dict[str, Any]) -> list[tuple[str, str]]:
    """(name, title) of every section the pane can show: each kind, then Skipped."""
    return [(k["name"], k["title"]) for k in board["kinds"]] + [(SKIPPED, "Skipped")]


def rows_of(board: dict[str, Any], section: str) -> list[Item]:
    if section == SKIPPED:
        return list(board["skipped"])
    return [it for it in board["items"] if it["kind"] == section]


def badge(item: Item, board: dict[str, Any]) -> str:
    if item.get("release"):
        return "RELEASE"
    return next((k["badge"] for k in board["kinds"] if k["name"] == item["kind"]), "ITEM")


def fit_dots(fit: int) -> str:
    return "●" * fit + "○" * (5 - fit)


def chips(item: Item) -> Line:
    """Facts the filter checked: green when good (✓), yellow when worth a look (!)."""
    out: Line = []
    if item.get("stars"):
        out.append(("★" + short_number(item["stars"]), "ok"))
    if "license" in item:
        out.append(("✓" + item["license"], "ok") if item["license"] else ("!no licence", "warn"))
    if "fresh" in item.get("why", []):
        out.append(("✓fresh", "ok"))
    return out


def header(board: dict[str, Any]) -> str:
    total = len(board["sources"])
    ok = sum(1 for s in board["sources"] if s["ok"])
    return (f"{board['title']} · {board['date']} · {len(board['items'])} kept · "
            f"{len(board['skipped'])} skipped · sources {ok}/{total} ok")


def tabs(board: dict[str, Any], current: str | None = None) -> Line:
    out: Line = []
    for n, (name, title) in enumerate(sections(board), 1):
        if out:
            out.append(("  ", "plain"))
        out.append((f"{n}:{title} {len(rows_of(board, name))}", "sel" if name == current else "head"))
    return out


def row(item: Item, board: dict[str, Any], name_width: int) -> Line:
    name = cut(item["title"], name_width).ljust(name_width)
    line: Line = [(badge(item, board).ljust(7), "badge"), (" ", "plain")]
    if "reason" in item:
        return line + [(name, "name"), ("  " + item["reason"], "warn")]
    line += [(fit_dots(item["fit"]), "dots"), (" ", "plain"), (name, "name")]
    for t, style in chips(item):
        line += [(" ", "plain"), (t, style)]
    return line


def section_lines(board: dict[str, Any], section: str) -> list[tuple[Line, Item | None]]:
    """The lines of one section: group headings (no item) and rows (with their item)."""
    rows = rows_of(board, section)
    width = min(NAME_MAX, max((len(r["title"]) for r in rows), default=4))
    out: list[tuple[Line, Item | None]] = []
    if section == SKIPPED:
        return [([("  ", "plain"), *row(r, board, width)], r) for r in rows]
    group = None
    for r in rows:
        if r["group"] != group:
            group = r["group"]
            count = sum(1 for x in rows if x["group"] == group)
            out.append(([(f"— {group.upper()} {count}", "head")], None))
        out.append(([("  ", "plain"), *row(r, board, width)], r))
    return out


def detail_lines(item: Item, width: int) -> list[Line]:
    """What the pane shows under the list for the selected item."""
    facts = [item["date"]] if item.get("date") else []
    if item.get("stars"):
        facts.append("★" + str(item["stars"]))
    if "fit" in item:
        facts.append(f"fit {item['fit']}/5")
    out: list[Line] = [[(cut(" · ".join([item["title"], *facts]), width), "name")]]
    found = chips(item)
    if found:
        line: Line = []
        for t, style in found:
            line += [(t, style), (" ", "plain")]
        out.append(line[:-1])
    if "reason" in item:
        out.append([("Skipped: " + item["reason"], "warn")])
    else:
        out += [[(t, "plain")] for t in wrap("Why: " + " · ".join(item["why"]), width)]
    out += [[(t, "plain")] for t in wrap(item.get("summary", ""), width)]
    out += [[(t, "dim")] for t in wrap(item["url"], width)]
    out.append([(cut(f"from {item['source']} · key {item['key']}", width), "dim")])
    return out


def text(line: Line) -> str:
    return "".join(t for t, _ in line).rstrip()


def board_text(board: dict[str, Any], width: int = 80) -> str:
    """The whole board as plain text: the preview, and `garden.py board`."""
    out = [header(board), text(tabs(board)), ""]
    for name, title in sections(board):
        lines = section_lines(board, name)
        if not lines:
            continue
        out.append(title.upper())
        out += [text(line) for line, _ in lines]
        out.append("")
    # `prompt` and `send` take a key. A repo's key is the name on its row; any
    # other item's key (link/...) is listed here, so the board shows them all.
    named = [it for it in [*board["items"], *board["skipped"]] if it["key"] != it["title"]]
    if named:
        out.append("KEYS (for prompt and send; a repo's key is its name)")
        out += [f"  {it['key']}  {cut(it['title'], max(width - len(it['key']) - 4, 10))}" for it in named]
        out.append("")
    failed = [s for s in board["sources"] if not s["ok"]]
    for s in failed:
        out.append(f"source failed: {s['name']}: {s['error']}")
    if failed:
        out.append("")
    first = next((it for it in board["items"]), None)
    if first is not None:
        out.append("The pane shows the selected item like this:")
        out += ["  " + text(line) for line in detail_lines(first, width - 2)]
        out.append("")
    out.append(KEYS)
    return "\n".join(out) + "\n"
