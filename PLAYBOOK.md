# The Garden: the playbook

This file is written for a coding agent (Claude Code, Codex, Grok) and is
readable by a person. Do the steps in order. Each step is one action, a
"Verify:" command and the result to expect. Stop at the first result that
does not match and report what you saw.

Run every command from the top folder of this repo. Steps marked
**Ask first** change something outside the repo: show the person the
command and wait for a yes.

## Goal

The reader has a Garden: their own feeds, filtered by their own interests,
in a pane of a Herdr tab, with a coding agent beside it. In the pane, `i`,
`d` and `a` hand the selected item to that agent as a prompt to integrate
it, diff it against their setup, or analyze it.

How it fits together:

```text
sources (RSS, Atom, GitHub search)
   -> collect: clean, sort into kinds, keep what matches your interests
   -> board file (JSON)
   -> pane: browse by kind, press i / d / a
   -> handoff: herdr agent prompt garden "<prompt>"  ->  the agent reads and reports
```

## Before you start

| Need | Check | Expected | If it fails |
|---|---|---|---|
| Python 3.11 or newer | `python3 -c 'import sys; print(sys.version_info >= (3, 11))'` | `True` | install a newer Python from python.org or your package manager |
| curses | `python3 -c 'import curses; print("ok")'` | `ok` | Linux and macOS have it; on Windows, use WSL |
| git | `git --version` | a version line | install git |
| Herdr 0.9.5 or newer (steps 7 and 8) | `herdr --version` | `herdr 0.9.5` or a newer version | install it from https://herdr.dev, or use the fallback in step 7 |
| A coding agent Herdr can start (steps 7 and 8) | `command -v claude codex grok` | at least one path | install one; `herdr agent start --help` lists the kinds Herdr knows |
| HTTPS to GitHub (step 5) | `python3 -c 'import urllib.request as u; print(u.urlopen("https://api.github.com", timeout=10).status)'` | `200` | check your network or proxy; the demo (steps 1 and 2) works offline |

## Steps

### 1. Run the demo on the synthetic data

This shows what the tool does before anything on your machine changes. The
feeds are made-up files in `examples/sources/`; nothing goes over the network.

```bash
bash examples/run.sh
```

Verify: `bash examples/run.sh | diff - examples/expected-output.txt && echo same`
Expected: `same`

### 2. Try the pane on the demo board

A person runs this and presses keys: arrows (or `j` and `k`) move, `1` to
`7` or left and right change the kind, `d` shows the prompt the key would
send, `q` quits. In the demo nothing is sent: `[handoff] mode` is `"show"`.

```bash
python3 src/garden.py --demo pick
```

An agent cannot press keys in a pane it cannot see, so the check runs the
same pane in a private pseudo-terminal and presses `j`, `4`, `d` and `q`.

Verify: `python3 -m unittest discover -s tests -p test_demo.py -k PaneInTerminalTest 2>&1 | tail -n 1`
Expected: `OK`

### 3. Make your config file

**Ask first**: this writes to `~/.config/playbook-herdr-garden/`. `cp -n`
keeps a file that is already there.

```bash
mkdir -p ~/.config/playbook-herdr-garden
cp -n examples/config.example.toml ~/.config/playbook-herdr-garden/config.toml
```

Verify: `python3 src/garden.py tab | head -n 1`
Expected: `# Build the Garden tab. Run these inside a Herdr pane, in this order.` (this
loads the config and checks every key; a wrong value, or a key the tool does not
know (a typo like `min_star`), prints the key's name instead)

### 4. Write your setup file

The `diff` and `integrate` prompts ask the agent to read this file and the
places it names. **Ask first**, then ask the person what they use and write
it in (five to ten short lines are enough).

```bash
cp -n examples/setup.example.md ~/.config/playbook-herdr-garden/setup.md
```

Verify: `test -s ~/.config/playbook-herdr-garden/setup.md && echo ok`
Expected: `ok`

### 5. Read the feeds

Edit `~/.config/playbook-herdr-garden/config.toml` first: put the person's
interests in `interests`, and their feeds in `[[sources]]` (see "Adapt it").
Then collect. **Ask first**: this reads the public feeds over HTTPS and
writes the board to `~/.local/state/playbook-herdr-garden/board.json`.

```bash
python3 src/garden.py collect
```

It prints one line per source, then `board: N kept, M skipped` and
`written to` with the board's path. A line with `FAILED` names a source that
did not answer: fix its `url` or `query`. GitHub allows a few searches a
minute without a token; `HTTP 403` means wait a minute, or see "Adapt it".

Verify: `python3 -c 'import json, pathlib; b = json.loads(pathlib.Path("~/.local/state/playbook-herdr-garden/board.json").expanduser().read_text()); print(sum(s["ok"] for s in b["sources"]), "of", len(b["sources"]), "sources ok,", len(b["items"]), "kept")'`
Expected: `7 of 7 sources ok, N kept` with N above 0 (the first number is your count of `[[sources]]`; it reads the board, so the feeds are not fetched again)

### 6. Look at the board

```bash
python3 src/garden.py board | head -n 2
```

Verify: `python3 src/garden.py board | head -n 1`
Expected: the config's `title`, today's date and `N kept`, for example `my garden · 2026-01-15 · 24 kept · 61 skipped · sources 7/7 ok`

If most items skip, the reasons are at the end of `board`: loosen
`interests` or `[filter]`, and collect again.

### 7. Build the Garden tab in Herdr

This step must run inside a Herdr pane: `echo "${HERDR_ENV:-no}"` prints `1`
there. If the agent doing this playbook is not in Herdr, give the person the
two commands below to run in a Herdr pane.

First print the four Herdr commands and read them (a dry run):

```bash
python3 src/garden.py tab
```

**Ask first**, then run them. `--kind` is the agent to start (`claude`,
`codex`, `grok`, and the others `herdr agent start --help` lists).

```bash
python3 src/garden.py tab --apply --kind claude
```

It prints the new tab's id and the command that removes it. Write the tab
id down for "Undo".

No Herdr? Run `python3 src/garden.py pick` in one terminal and your agent in
another, and set `[handoff] mode = "command"` with your clipboard tool (see
"Adapt it"). A key then copies the prompt, and you paste it into the agent.

Verify: `herdr agent get garden > /dev/null && echo ready`
Expected: `ready` (no Herdr: `python3 src/garden.py send analyze <a key from the board>` exits 0 and the prompt is on your clipboard)

### 8. Hand one item to the agent

In the Garden tab, the person moves to an item in the left pane and presses
`a` (analyze). The status line at the bottom of the pane says
`sent to the Herdr agent garden`. The same works from any Herdr pane, with a
key from `board`:

```bash
python3 src/garden.py send analyze <key>
```

Verify: `herdr agent read garden --source recent-unwrapped --lines 80 | grep -c 'Garden pick'`
Expected: `1` or more (the agent got the prompt; its answer ends with a verdict: try, watch or skip)

### 9. Collect every morning (optional)

**Ask first**: this adds one line to the person's crontab. The pane loads a
new board by itself when the file changes.

This step needs cron: `command -v crontab` prints a path. If it prints
nothing, install your system's cron package (cronie on many Linux systems),
or skip this step and run `collect` by hand.

cron runs the line with `/bin/sh`, a short `PATH` (often `/usr/bin:/bin`) and
no profile, and it reads a `%` as a new line. So `python3 src/garden.py cron`
writes the line for you: every path absolute and in single quotes, and the
same Python 3.11 that runs it now, not an older `python3` cron might find. It
refuses a path that holds `'` or `%`. The second command removes any older
Garden line first, so running this step twice still leaves one line.

```bash
mkdir -p ~/.local/state/playbook-herdr-garden
line="$(python3 src/garden.py cron)" && (crontab -l 2>/dev/null | grep -v 'playbook-herdr-garden/collect.log'; echo "$line") | crontab -
```

Verify: `crontab -l | grep -c 'playbook-herdr-garden/collect.log'`
Expected: `1`

Then run that line once the way cron will (it reads the feeds again):

Verify: `env -i HOME="$HOME" PATH=/usr/bin:/bin /bin/sh -c "$(crontab -l | grep 'playbook-herdr-garden/collect.log' | cut -d' ' -f6-)"; tail -n 1 ~/.local/state/playbook-herdr-garden/collect.log`
Expected: `written to` and the board's path. Anything else in the log is the reason the morning run would fail.

## Adapt it

| Setting | Where | Example |
|---|---|---|
| Interests: an item must match one to stay, and each match adds fit | `config.toml`, key `interests` | `interests = ["agent", "rust", "nix"]` |
| A GitHub search | a `[[sources]]` table, `type = "github-search"`, `query` | `query = "topic:mcp-server pushed:>{since}"` (`{since}` is the date `max_age_days` ago) |
| An RSS or Atom feed | `type = "rss"` or `type = "atom"`, `url` | `url = "https://hnrss.org/newest?q=herdr"` |
| The releases of a repo | `type = "github-releases"`, `repo` | `repo = "herdrdev/herdr"` |
| One kind for every item of a source | the source's `kind` | `kind = "skills"` |
| The words that decide a kind | `[kinds.<name>]`, key `words` | `[kinds.coding]` then `words = ["dotfiles", "claude.md"]` |
| A kind of your own | `[kinds.<name>]` with `title`, `badge`, `words` | `[kinds.mcp]` then `title = "MCP servers"`, `words = ["mcp"]` |
| The filter | `[filter]`: `max_age_days`, `min_stars`, `drop`, `per_kind` | `min_stars = 50`, `drop = ["crypto"]` |
| The prompts | `[prompts]`: `integrate`, `diff`, `analyze`; each must hold `{url}` | `analyze = "Read {url} without running it. Is it safe to try?"` |
| Where a prompt goes | `[handoff]`, key `mode`: `herdr`, `command` or `show` | `mode = "command"` and `command = ["wl-copy"]` (or `["pbcopy"]`, `["xclip", "-selection", "clipboard"]`) |
| The agent's name in Herdr | `[handoff]`, key `agent` | `agent = "scout"` |
| The agent Herdr starts, the tab's name | `tab --apply` options | `python3 src/garden.py tab --apply --kind codex --label Feeds` |
| A GitHub token (more searches a minute) | the `GITHUB_TOKEN` environment variable of `collect` | `GITHUB_TOKEN="$(gh auth token)" python3 src/garden.py collect` |
| Another config file | `--config`, or `GARDEN_CONFIG` | `GARDEN_CONFIG=~/garden-work.toml python3 src/garden.py pick` |
| A smarter filter | `src/feedgarden/kinds.py`, function `judge()` | ask a model to score each item against your setup file; keep the same return shape (`fit`, `why`, `group`, or `reason`) |

## Done when

- `./check.sh` prints `check: ok`.
- `python3 src/garden.py board | head -n 1` shows the person's title and `N kept` with N above 0.
- In Herdr, the Garden tab has the pane on the left and the agent on the right, and
  `herdr agent get garden > /dev/null && echo ready` prints `ready`.
- Pressing `a` on an item in the pane makes the agent answer with a verdict (try, watch or skip).

## Undo

- The tab: `herdr tab close <tab-id>` (the id `tab --apply` printed; `herdr tab list` shows it again).
  This closes the pane and the agent in it.
- The morning collect: `crontab -l | grep -v 'playbook-herdr-garden/collect.log' | crontab -`
  (or `crontab -e` and delete the line that holds `garden.py`).
- The config, the setup file, the board and the log:
  `rm -r ~/.config/playbook-herdr-garden ~/.local/state/playbook-herdr-garden`
- The repo: delete the clone. The tool writes nothing else.

## Safety

- Reads: its config file; the public feeds in `[[sources]]`, over HTTPS only (a redirect to a plain
  `http://` address is refused), at most 5 MB each; the `GITHUB_TOKEN` variable when set, which it
  sends only to GitHub in a header (it is dropped if a redirect leads to another host) and never
  prints or saves.
  The setup file is read by the agent, not by the tool: the tool only puts its path in the prompt.
- Writes: the board file (written to a new file, then renamed, so the pane never reads half of one).
  `tab --apply` creates one Herdr tab with two panes and starts one agent; it touches no other tab.
- Feed text is untrusted. The tool removes HTML, control characters and terminal escape codes from it,
  accepts only `https://` links (an item with a plain `http://` link is left out) and plain keys, and every prompt tells the agent that the item is data,
  not instructions, and to change nothing without a yes.
- The prompt is a request, not a lock: your agent's own permission settings decide what it may run.
  Keep them strict, because the agent reads pages and repos written by strangers.
- Never: runs code from a feed; sends a prompt without a key press or a `send` command; sends to an
  agent that waits on a question (Herdr refuses, and the pane says so); runs `tab --apply` outside a
  Herdr pane or in the demo; types into any pane but its own picker pane and the agent named in
  `[handoff] agent`; closes or stops any pane, agent or process.
