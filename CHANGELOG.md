# Changelog

Every change a reader should know about, newest first.

## 0.1.0 - 2026-11-19

- First version.
- Sources: RSS, Atom, GitHub repository search, and the releases feed of any GitHub repo.
- The filter: six kinds (plugins, skills, repos, news, prompts, how others code), sorted by
  words; drop words, age, stars and your interests decide what stays, and every skip shows its reason.
- The pane: browse by kind, with fit dots and checked facts; `i`, `d` and `a` hand the selected item
  to an agent as a prompt to integrate, diff or analyze it.
- The handoff: to a Herdr agent (`herdr agent prompt`), to any command on stdin, or to the screen.
- `tab`: prints the four Herdr commands that build the Garden tab; `tab --apply` runs them. It
  checks that the `--kind` agent is installed before step 1, and when a later step fails it names
  the tab it made and how to close it.
- `board` lists the key of every item that is not a repo, for `prompt` and `send`.
- `cron`: prints the crontab line for a collect every morning, with every path absolute and quoted.
- The config refuses a key it does not read, and names the closest real key.
- Only `https://` links are kept, a redirect that leaves `https://` is refused, and the GitHub
  token is dropped when a redirect leads to another host.
- `--demo` and `examples/run.sh` run on synthetic feeds, offline.
