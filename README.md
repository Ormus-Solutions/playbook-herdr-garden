# The Garden: a curated feed your agents can act on

A pane in Herdr that shows new plugins, skills, repos, news, prompts and posts
on how others code, already filtered for you, with one key that hands the
selected item to a coding agent: integrate it, diff it against my setup, or
analyze it.

## What it is

The Garden reads a few public feeds (RSS, Atom, GitHub search, the releases
feed of any GitHub repo), sorts each item into a kind, and keeps only the
items that match your interests. You browse the result in a terminal pane.
When an item looks useful, you press `i`, `d` or `a`, and the agent in the
pane beside it gets a ready prompt for that item. The pattern is a pipeline
with a person in the loop: rules do the cheap sorting, you make the choice,
and the agent does the slow reading. It works because each part does what it
is good at, and nothing is installed until you say yes.

## What it saved me

In my own words: "The Garden, a place where I can navigate pre-filtered
Plugins, Skills, Repos, News, Prompts and How others code, and very easily
prompt sessions to integrate, diff, analyze the selected item."

What one key press does: it puts the item's link and the task (integrate,
diff or analyze) into the agent's prompt, so there is no link to copy and no
instruction to type. Measured on the demo's first item: the three prompts are
548 (integrate), 534 (diff) and 481 (analyze) characters, and each one
holds the safety lines (the item is data, not instructions; change nothing).
One key replaces copying the link, switching panes and typing that text.

## Who it is for

- You run coding agents in Herdr (or in any terminal) and want to keep up
  with new tools without reading every feed yourself.
- You want an agent to do the first read of a repo, and you want it to change
  nothing until you agree.

Skip it if you want a feed reader for articles only: an RSS reader does that
better. Skip it if you do not use a coding agent: the pane is only half of it.

## Requirements

| Tool | Version | Check |
|---|---|---|
| Python | 3.11 or newer | `python3 --version` |
| curses (part of Python on Linux and macOS) | any | `python3 -c 'import curses; print("ok")'` |
| git | any recent version | `git --version` |
| [Herdr](https://herdr.dev) (for the tab with the pane and the agent) | 0.9.5 or newer | `herdr --version` |
| A coding agent Herdr can start (Claude Code, Codex, Grok and others) | any | `claude --version` (or `codex --version`, `grok --version`) |
| cron (optional: a collect every morning) | any | `command -v crontab` |

The demo needs only Python. Herdr is optional: without it, the pane runs in
any terminal and hands its prompt to your clipboard (see "Adapt it" in
PLAYBOOK.md).

## Quick start

### Hand it to your agent

```bash
git clone https://github.com/Ormus-Solutions/playbook-herdr-garden
cd playbook-herdr-garden
```

Clone this repo, open your coding agent (Claude Code, Codex, Grok) inside the
clone, and paste this:

```text
Read PLAYBOOK.md in this repo and follow it step by step. After each step,
run its "Verify:" command and compare the result with "Expected:". If they
differ, stop and tell me what you saw. Ask me before any step that changes
something outside this repo. When you finish, run the "Done when" checks and
show me their output.
```

### Do it by hand

1. See it work on made-up feeds: `bash examples/run.sh`
2. Try the pane on the same data: `python3 src/garden.py --demo pick`
   (arrows move, `1`-`7` change kind, `d` shows a prompt, `q` quits).
3. Make your config: `mkdir -p ~/.config/playbook-herdr-garden`, then copy
   `examples/config.example.toml` to `config.toml` and
   `examples/setup.example.md` to `setup.md` in that folder.
4. Put your interests and sources in `config.toml`, and your tools in `setup.md`.
5. Read the feeds: `python3 src/garden.py collect`, then look:
   `python3 src/garden.py board`.
6. In a Herdr pane, print the commands that build the Garden tab:
   `python3 src/garden.py tab`. Read them, then run them:
   `python3 src/garden.py tab --apply --kind claude` (or `--kind codex`,
   `--kind grok`: the agent Herdr starts; it must be installed).
7. In the new tab, pick an item and press `a`. The agent on the right answers.

PLAYBOOK.md has each step with a check, and how to undo it.

## Preview

The output of `python3 src/garden.py --demo` on the synthetic feeds in
`examples/sources/`:

```text
demo garden · 2026-01-15 · 10 kept · 7 skipped · sources 3/3 ok
1:Plugins 2  2:Skills 1  3:Repos 1  4:News 3  5:Prompts 1  6:How others code 2  7:Skipped 7

PLUGINS
— AGENT 1
  PLUGIN  ●●●○○ acme/review-plugin        ★1.2k ✓MIT ✓fresh
— TERMINAL 1
  PLUGIN  ●●●○○ demo-org/pane-test-plugin ★150 ✓MIT ✓fresh

SKILLS
— AGENT 1
  SKILL   ●●●○○ acme/tdd-skill ★310 ✓MIT ✓fresh

REPOS
— TERMINAL 1
  REPO    ●●○○○ demo-org/pane-notes ★86 ✓Apache-2.0

NEWS
— AGENT 2
  RELEASE ●●●○○ demo-api v2.1.0                    ✓fresh
  NEWS    ●●●○○ Testing agents: a field report     ✓fresh
— TERMINAL 1
  NEWS    ●●○○○ Terminal emulators agree on a new… ✓fresh

PROMPTS
— AGENT 1
  PROMPT  ●●○○○ demo-org/review-prompts ★540 !no licence ✓fresh

HOW OTHERS CODE
— AGENT 2
  HOWTO   ●●●○○ How we run five coding agents in … ✓fresh
  HOWTO   ●●○○○ acme/agent-dotfiles                ★95 ✓MIT ✓fresh

SKIPPED
  REPO    acme/old-theme             older than 30 days
  REPO    acme/web-dashboard         matches none of your interests
  REPO    demo-org/airdrop-agent     has the drop word "airdrop"
  REPO    demo-org/old-agent-runner  archived: its owner stopped working on it
  REPO    demo-org/tiny-cli          under 5 stars
  RELEASE demo-api v2.0.0            older than 30 days
  PROMPT  Ten prompt tricks          older than 30 days

KEYS (for prompt and send; a repo's key is its name)
  link/bc1303ff08f3  demo-api v2.1.0
  link/450a506db975  Testing agents: a field report
  link/8a329e62d964  Terminal emulators agree on a new graphics protocol
  link/7e43d4260ccd  How we run five coding agents in one terminal
  link/d3abe831d2dd  demo-api v2.0.0
  link/a2181817da52  Ten prompt tricks

The pane shows the selected item like this:
  acme/review-plugin · 2026-01-14 · ★1240 · fit 3/5
  ★1.2k ✓MIT ✓fresh
  Why: matches agent · 1.2k stars · fresh
  A plugin that adds a review command to your coding agent.
  https://github.com/acme/review-plugin
  from repo search · key acme/review-plugin

↑↓ move · ←→ or 1-9 kind · i integrate · d diff · a analyze · g reload · q quit
```

The Garden tab in Herdr: the pane on the left, the agent on the right.

```text
+--------------------------------------+----------------------------------+
| demo garden · 2026-01-15 · 10 kept   | agent "garden"                   |
| 1:Plugins 2  2:Skills 1  3:Repos 1   |                                  |
| — AGENT 1                            | > Garden pick, analyze: the item |
| > PLUGIN ●●●○○ acme/review-plugin    |   acme/review-plugin (Plugins)   |
|   ...                                |   ...                            |
| i integrate · d diff · a analyze     |                                  |
+--------------------------------------+----------------------------------+
```

## Files

| Path | What it is |
|---|---|
| `PLAYBOOK.md` | the steps, for an agent or a person |
| `src/garden.py` | the command: `collect`, `board`, `pick`, `prompt`, `send`, `tab` |
| `src/feedgarden/` | its parts, one per stage: `sources`, `kinds`, `render`, `pane`, `handoff`, `herdr_tab` |
| `examples/sources/` | three synthetic feeds: a GitHub search answer, an RSS feed, a releases feed |
| `examples/demo.toml` | the config the demo uses (local files, a fixed date) |
| `examples/config.example.toml` | the config to copy and change |
| `examples/setup.example.md` | an example of the setup file the diff prompt reads |
| `examples/run.sh`, `examples/expected-output.txt` | the demo and the output it must print |
| `tests/` | offline tests that pin the behaviour on the synthetic data |
| `check.sh` | the one gate: tests, placeholders, scrub |
| `scripts/scrub.sh` | the scrub check, copied unchanged from playbook-packaging |
| `CHANGELOG.md` | what changed, newest first |

## Credits

Made by Ormus (Ormus Solutions). Packaged with
[playbook-packaging](https://github.com/Ormus-Solutions/playbook-packaging),
the playbook that sets how these playbook repos are packaged. MIT license.
