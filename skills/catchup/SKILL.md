---
name: catchup
description: Produce a short "getting back into this project" report - overview, unfinished notes, git state, and how to best interact with the output (data files, local HTML, npm dev server, GitHub Pages, or Vercel). Use whenever the user asks to catch up, resume, get oriented, or asks "what's the status of this project" at the start of a session.
---

# catchup

Run this in the current project directory (the user's cwd, or a path they name).
Goal: get someone who has not touched this project in a while oriented in under
a minute. Be concise - this is a scan-and-orient report, not a deep dive. Do
not modify any files.

## 1. Overview

Read `CLAUDE.md` if present, else `README.md`. Pull the title/first paragraph
and a one-line sense of what the project is and how it's deployed (these files
often have a "Deploying" or "Architecture" section - skim, don't reproduce it
verbatim).

## 2. Unfinished notes

Look for a `## Status` section in `CLAUDE.md` (this is the convention: a
running "where things stand / what's next" note the user leaves for their
future self at the end of a work session). If found, surface it near-verbatim
- it's the single most important part of the report.

If there is no `## Status` section, say so plainly ("no status notes left")
rather than inventing one from git history. Optionally fall back to a `TODO`/
`NOTES.md` file if one exists.

## 3. Git state

From the project root (find it with `git rev-parse --show-toplevel` if cwd is
a subdirectory):

- Current branch, and whether it has an upstream.
- `git status --short` - uncommitted or untracked work. Call this out clearly;
  it's often the most important sign that a session ended mid-thought.
- `git log -5 --oneline` - recent commits, for a sense of momentum/direction.
- If there's an upstream, whether local is ahead/behind it
  (`git log @{u}.. --oneline` and `git log ..@{u} --oneline`).

If the directory isn't a git repo at all, say so and skip this section.

## 4. How to best interact with this project

Inspect the project for signals and report ONE primary recommendation (plus
alternates only if genuinely ambiguous). Check in this order and use the
first that fits - projects often have more than one signal, so prefer the one
that matches how the project actually gets *used* day to day, not just what
tooling exists:

- **Vercel** - `vercel.json`, a `.vercel/` directory, or a Vercel URL/mention
  in CLAUDE.md/README. Report the project name/URL if findable and that
  `vercel dev` or a `git push` triggers deploy.
- **GitHub Pages / web** - CLAUDE.md/README mentions a `github.io` URL, or
  there's a `docs/` folder plus Pages-style deploy notes, or a `gh-pages`
  branch (`git branch -a | grep gh-pages`). Report the live URL and that
  push-to-deploy is the whole loop.
- **npm / local dev server** - a `package.json` with a `dev`, `start`, or
  `serve` script. Report the exact command (`npm install && npm run dev`,
  reading the actual script name rather than assuming "dev").
- **Local HTML in the browser** - a standalone `index.html` (often under
  `docs/` or similar) with no build step. Report how to open/serve it (e.g.
  `python3 -m http.server` from that directory, per this project's own
  instructions if it states one - don't invent a different one).
- **Data files** - the project is primarily scripts/notebooks/CSV/JSON with
  no served UI. Report the entry-point script(s) and where output lands.

## Output format

Keep the whole report tight - headers plus a few bullets each, not prose
paragraphs:

```
## <Project name>
<one-line description>

### Status
<contents of the ## Status section, or "No status notes left.">

### Git
- branch: ... (ahead/behind, if applicable)
- uncommitted: ... (or "clean")
- recent: <last few commits, one line each>

### How to interact
<the one recommended mode, with the exact command(s)>
```

If asked to run this across multiple project directories, produce one such
block per project, not a single merged summary.
