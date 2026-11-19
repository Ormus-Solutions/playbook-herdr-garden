"""Read the sources into items.

A source is an RSS feed, an Atom feed (GitHub publishes one for the releases
of every repo), or a GitHub repository search. Each parser is a pure
function: text in, a list of items out. Only fetch() touches the network,
and the demo and the tests never call it.

An item is a plain dict:
    key      owner/repo or link/<12 hex> (see text.key_for)
    title    cleaned text
    url      https:// link
    summary  cleaned text
    date     YYYY-MM-DD, or "" when the feed gave none
    source   the source's name
    hint     the source's kind, or ""
    stars    a number (GitHub only), else None
    license  an SPDX id, "" for none (GitHub only); absent for other items
    archived True when the repo is read only (GitHub only)
    release  True for an entry of a releases feed
"""
from __future__ import annotations

import datetime as dt
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable
from email.utils import parsedate_to_datetime
from typing import Any

from feedgarden.config import Config, Source
from feedgarden.text import clean, key_for, url_ok

Item = dict[str, Any]
Fetch = Callable[[str, dict[str, str]], str]
MAX_BYTES = 5_000_000
ATOM = "{http://www.w3.org/2005/Atom}"
GITHUB_API = "https://api.github.com/search/repositories"


class SourceError(Exception):
    """A source could not be read. The run goes on with the other sources."""


def _date(raw: str | None) -> str:
    """Any feed date (RFC 822 in RSS, ISO 8601 in Atom and GitHub) as YYYY-MM-DD."""
    if not raw:
        return ""
    raw = raw.strip()
    try:
        return dt.datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(raw).date().isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def _xml(text: str) -> ET.Element:
    # A feed never needs its own entities. Refusing them blocks the "billion
    # laughs" trick, where a few lines of XML expand to gigabytes.
    if "<!ENTITY" in text:
        raise SourceError("the feed declares XML entities; refused")
    try:
        return ET.fromstring(text)
    except ET.ParseError as e:
        raise SourceError(f"not valid XML ({e})") from None


def _item(title: Any, url: Any, summary: Any, date: str, **extra: Any) -> Item | None:
    url = clean(url, 500)
    title = clean(title, 160)
    if not url_ok(url) or not title:
        return None  # an entry with no usable link cannot be acted on
    return {"key": key_for(url), "title": title, "url": url, "summary": clean(summary, 400),
            "date": date, **extra}


def parse_rss(text: str) -> list[Item]:
    root = _xml(text)
    out = []
    for node in root.iter("item"):
        it = _item(node.findtext("title"), node.findtext("link"), node.findtext("description"),
                   _date(node.findtext("pubDate")))
        if it:
            out.append(it)
    return out


def parse_atom(text: str) -> list[Item]:
    root = _xml(text)
    out = []
    for node in root.iter(f"{ATOM}entry"):
        link = ""
        for ln in node.findall(f"{ATOM}link"):
            if ln.get("rel", "alternate") == "alternate":
                link = ln.get("href", "")
                break
        summary = node.findtext(f"{ATOM}summary") or node.findtext(f"{ATOM}content") or ""
        date = _date(node.findtext(f"{ATOM}updated") or node.findtext(f"{ATOM}published"))
        it = _item(node.findtext(f"{ATOM}title"), link, summary, date)
        if it:
            out.append(it)
    return out


def parse_github_search(text: str) -> list[Item]:
    try:
        data = json.loads(text)
    except ValueError:
        raise SourceError("the GitHub answer is not JSON") from None
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise SourceError(clean(data.get("message") if isinstance(data, dict) else "", 120)
                          or "the GitHub answer has no items")
    out = []
    for repo in data["items"]:
        if not isinstance(repo, dict):
            continue
        lic = repo.get("license") if isinstance(repo.get("license"), dict) else {}
        spdx = clean(lic.get("spdx_id"), 40)
        topics = [clean(t, 40) for t in repo.get("topics") or [] if isinstance(t, str)]
        stars = repo.get("stargazers_count")
        it = _item(repo.get("full_name"), repo.get("html_url"), repo.get("description"),
                   _date(repo.get("pushed_at") or repo.get("created_at")),
                   stars=stars if isinstance(stars, int) else 0,
                   license="" if spdx in ("", "NOASSERTION") else spdx,
                   topics=topics,
                   archived=repo.get("archived") is True)
        if it:
            out.append(it)
    return out


def fetch(url: str, headers: dict[str, str]) -> str:
    """GET a URL and return its text. The only function that uses the network."""
    req = urllib.request.Request(url, headers={"User-Agent": "playbook-herdr-garden", **headers})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            body = resp.read(MAX_BYTES + 1)
    except urllib.error.HTTPError as e:
        raise SourceError(f"HTTP {e.code}") from None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise SourceError(clean(getattr(e, "reason", e), 120)) from None
    if len(body) > MAX_BYTES:
        raise SourceError("the answer is bigger than 5 MB")
    return body.decode("utf-8", errors="replace")


def github_search_url(query: str, since: str) -> str:
    q = query.replace("{since}", since)
    params = {"q": q, "sort": "updated", "order": "desc", "per_page": "30"}
    return GITHUB_API + "?" + urllib.parse.urlencode(params)


def read_source(src: Source, cfg: Config, today: str, get: Fetch = fetch) -> list[Item]:
    """All items of one source, each marked with the source's name and kind."""
    since = (dt.date.fromisoformat(today) - dt.timedelta(days=cfg.max_age_days)).isoformat()
    if src.path is not None:
        try:
            text = src.path.read_text(encoding="utf-8")
        except OSError as e:
            raise SourceError(f"cannot read {src.path.name}: {e.strerror}") from None
    elif src.type == "github-search":
        headers = {"Accept": "application/vnd.github+json"}
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:  # optional: a token lifts GitHub's limit for searches without one
            headers["Authorization"] = "Bearer " + token
        text = get(github_search_url(src.query, since), headers)
    elif src.type == "github-releases":
        text = get(f"https://github.com/{src.repo}/releases.atom", {})
    else:
        text = get(src.url, {})

    if src.type == "rss":
        items = parse_rss(text)
    elif src.type == "github-search":
        items = parse_github_search(text)
    else:
        items = parse_atom(text)
    for it in items:
        it["source"] = src.name
        it["hint"] = src.kind
        if src.type == "github-releases":
            it["release"] = True
            name = src.repo.split("/")[1]
            if not it["title"].lower().startswith(name.lower()):
                it["title"] = clean(f"{name} {it['title']}", 160)
    return items


def collect(cfg: Config, today: str, get: Fetch = fetch) -> tuple[list[Item], list[dict[str, Any]]]:
    """Read every source. A source that fails is reported, and the others still count.

    This is called "fail soft": one feed that is down must not empty the board.
    """
    items: list[Item] = []
    report: list[dict[str, Any]] = []
    for src in cfg.sources:
        try:
            got = read_source(src, cfg, today, get)
        except SourceError as e:
            report.append({"name": src.name, "ok": False, "found": 0, "error": str(e)})
            continue
        items.extend(got)
        report.append({"name": src.name, "ok": True, "found": len(got)})
    return items, report
