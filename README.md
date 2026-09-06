# claude-dotfiles

Personal Claude Code configuration, kept in git so it's identical on every
machine.

## Contents

- `skills/catchup/` — the `/catchup` skill: a "get me oriented in this
  project again" report (overview, unfinished `## Status` notes, git state,
  and how to best interact with the project's output).

## Setup on a new machine

```
git clone https://github.com/cshirky/claude-dotfiles.git ~/claude-dotfiles
mkdir -p ~/.claude
ln -s ~/claude-dotfiles/skills ~/.claude/skills
```

If `~/.claude/skills` already exists and isn't a symlink, move its contents
into `~/claude-dotfiles/skills/` first, then create the symlink.

## Adding a new skill later

Add a new folder under `skills/`, commit, push, and `git pull` on the other
machines — no re-symlinking needed.

## Per-project convention this depends on

`/catchup` looks for a `## Status` section at the bottom of a project's
`CLAUDE.md` — a few lines you leave for your future self before ending a
session: what's unfinished, what you were mid-thought on, what to look at
next. No section there just means the report says "no status notes left."
