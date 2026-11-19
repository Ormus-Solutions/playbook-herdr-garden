"""Sort items into kinds, keep the useful ones, and build the board.

This is the "pre-filter": rules decide, so it runs offline and gives the same
board for the same feeds. Each kept item carries its reasons ("why"), and
each skipped item carries the rule that skipped it. Nothing is dropped
without a trace, so you can see when a rule is too strict and change it.

The rules, in order:
1. a drop word in the item skips it, and so does an archived repo;
2. an item older than max_age_days skips (an item with no date stays);
3. a GitHub repo under min_stars skips;
4. an item that matches none of your interests skips;
5. each kind keeps its per_kind best; the rest skip.

The fit (1 to 5) is: one point per interest it matches, one more for 1000
stars or more, one more when it is fresh (7 days or less).
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from feedgarden.config import Config
from feedgarden.sources import Item
from feedgarden.text import short_number, starts_word

FRESH_DAYS = 7
POPULAR_STARS = 1000


def _text(item: Item) -> str:
    return " ".join([item.get("title", ""), item.get("summary", ""), *item.get("topics", [])])


def classify(item: Item, kinds: dict[str, dict[str, Any]]) -> str:
    """The kind of an item: the source's hint, else the first kind whose word it has."""
    if item.get("hint") in kinds:
        return str(item["hint"])
    text = _text(item)
    for name, spec in kinds.items():
        if any(starts_word(w, text) for w in spec.get("words", [])):
            return name
    return "repos" if "stars" in item else "news"


def age_days(item: Item, today: str) -> int | None:
    if not item.get("date"):
        return None
    return (dt.date.fromisoformat(today) - dt.date.fromisoformat(item["date"])).days


def judge(item: Item, cfg: Config, today: str) -> dict[str, Any]:
    """Keep or skip one item. Returns {"reason"} for a skip, else {"fit", "why", "group"}."""
    text = _text(item)
    for word in cfg.drop:
        if starts_word(word, text):
            return {"reason": f'has the drop word "{word}"'}
    if item.get("archived"):
        return {"reason": "archived: its owner stopped working on it"}
    age = age_days(item, today)
    if age is not None and age > cfg.max_age_days:
        return {"reason": f"older than {cfg.max_age_days} days"}
    stars = item.get("stars")
    if stars is not None and stars < cfg.min_stars:
        return {"reason": f"under {cfg.min_stars} stars"}
    matched = [w for w in cfg.interests if starts_word(w, text)]
    if not matched:
        return {"reason": "matches none of your interests"}
    why = ["matches " + ", ".join(matched)]
    fit = len(matched)
    if stars is not None and stars >= POPULAR_STARS:
        fit += 1
        why.append(f"{short_number(stars)} stars")
    if age is not None and age <= FRESH_DAYS:
        fit += 1
        why.append("fresh")
    return {"fit": min(fit, 5), "why": why, "group": matched[0]}


def _rank(item: Item) -> tuple[int, int, int, str]:
    day = dt.date.fromisoformat(item["date"]).toordinal() if item.get("date") else 0
    return (-item["fit"], -(item.get("stars") or 0), -day, item["key"].lower())


def build_board(items: list[Item], report: list[dict[str, Any]], cfg: Config, today: str) -> dict[str, Any]:
    """The board: the kept items by kind and group, the skipped ones with their reason."""
    seen: set[str] = set()
    kept: dict[str, list[Item]] = {k: [] for k in cfg.kinds}
    skipped: list[Item] = []
    for item in items:
        low = item["key"].lower()
        if low in seen:
            continue  # the same repo from two sources shows once
        seen.add(low)
        item = {**item, "kind": classify(item, cfg.kinds)}
        verdict = judge(item, cfg, today)
        if "reason" in verdict:
            skipped.append({**item, **verdict})
        else:
            kept[item["kind"]].append({**item, **verdict})

    order = {w: i for i, w in enumerate(cfg.interests)}
    board_items: list[Item] = []
    for kind, rows in kept.items():
        ranked = sorted(rows, key=_rank)
        for extra in ranked[cfg.per_kind:]:
            skipped.append({k: v for k, v in extra.items() if k not in ("fit", "why", "group")}
                           | {"reason": f"past the {cfg.per_kind} best of its kind"})
        best = ranked[: cfg.per_kind]
        board_items += sorted(best, key=lambda r: (order[r["group"]], *_rank(r)))

    kind_order = {k: i for i, k in enumerate(cfg.kinds)}
    skipped.sort(key=lambda r: (kind_order[r["kind"]], r["key"].lower()))
    return {
        "title": cfg.title,
        "date": today,
        "kinds": [{"name": k, "title": v["title"], "badge": v["badge"]} for k, v in cfg.kinds.items()],
        "sources": report,
        "items": board_items,
        "skipped": skipped,
    }
