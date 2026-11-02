---
name: gh-review
description: Inventory every GitHub repo in the cshirky account - name, a one-line precis of what it's for, how it can be served (local webserver, github.io, or Vercel/DigitalOcean/other hosting), and the date and name of the most recently changed file. Cached locally so unchanged repos aren't re-fetched. Use when the user runs /gh-review or asks for an overview/list of all their GitHub repos.
---

# gh-review

All the GitHub work is done by `gh-review.py`, which sits next to this file.
Run it as `python3 ~/.claude/skills/gh-review/gh-review.py <subcommand>`.
Your only job is writing the precis lines and presenting the report. Don't
modify any repo.

Pass `--owner <name>` to every subcommand if the user names a different
account. Pass `--refresh` to `scan` only if the user asks for a full re-check.

## 1. Scan

```
python3 ~/.claude/skills/gh-review/gh-review.py scan
```

This lists every repo with `gh repo list`, then compares each one's
`pushedAt`/`updatedAt` with the cache at `~/.cache/gh-review/<owner>.json`.
It re-fetches only new or changed repos: last commit, files in that commit,
file tree, Pages status, deployments, README. Deleted repos are dropped from
the cache. It prints JSON with `rechecked`, `failed`, `unchanged`,
`removed`, and `need_precis`.

A repo in `failed` (rate limit, network error) keeps its previous cache
entry and is retried next run. Name the failed repos in the report's summary
line so stale rows aren't mistaken for current ones.

## 2. Write a precis for each entry in `need_precis`

If `need_precis` is empty, skip to step 3.

Each entry has `description`, `readme_excerpt` (the README, or CLAUDE.md
when the README is thin, or the `index.html` title when neither exists), and
`top_level` (the top-level file names). Write one plain sentence per repo of
about 20 words or fewer, saying what the repo is for. Rules:

- Say "Fork of …" for forks of other people's projects, "Learn.co
  coursework: …" for course labs, and "Empty repo." for empty ones.
- Name the framework only when you've seen it (README or `top_level`).
  Don't guess.
- If there's nothing to go on, say what the files suggest ("Python
  scripts and CSVs on …; no README") rather than inventing a purpose.

Write all of them to one JSON file `{"repo": "precis", ...}` in the
scratchpad, then store them:

```
python3 ~/.claude/skills/gh-review/gh-review.py set-precis <file>
```

A stored precis is kept until the repo's README or description changes.

## 3. Report

```
python3 ~/.claude/skills/gh-review/gh-review.py report
```

This prints a markdown table, newest change first: repo (linked, flagged
private/fork/archived), precis, serving options, and last change (date plus
the first file in the most recent commit, "+N more" if the commit touched
others). Show the table as printed. Above it, add one line:
`42 repos — 3 rechecked, 39 from cache` (use the real numbers, and list
the rechecked names if there are only a few).

How to read the Serving column:
- `github.io: <url>` means Pages is enabled (from the Pages API) or the
  homepage is a github.io URL on this account.
- Vercel, Netlify, DigitalOcean, Fly.io, Render, Cloudflare, Firebase and
  Heroku are detected from config files (`vercel.json`, `.do/`, `fly.toml`,
  `Procfile` …), the homepage URL, and GitHub deployment records.
- `local:` means an npm dev/start/serve/preview script, a Django, Flask,
  Streamlit, FastAPI or Dash app, Jekyll, or a shallow `index.html` that
  `python3 -m http.server` can serve.

After the table, add at most three short observations if any stand out,
such as a live site in a repo with no recent commits, or near-duplicate
repos. Skip them if nothing stands out.
