# Personal Claude Code instructions

Applies to every project. Kept in git so it's identical on every machine — see
`README.md` for the symlink that puts this in `~/.claude/`.

## Report local servers as full, clickable URLs

When reporting that a dev server — or anything else serving locally — is
running, print the complete URL, not just the port:

```
yes:  http://localhost:3000
no:   running on port 3000
no:   localhost:3000
```

Terminals linkify a complete URL, so a full one is a single click instead of
something to retype or assemble by hand.

- Link the specific page when there is an obvious one to look at:
  `http://localhost:3000/institutions` rather than the bare root.
- This covers any locally served thing, not just Next/Vite: `python3 -m
  http.server`, Storybook, a preview build, a served HTML file, a docs site.
- Hand over the `localhost` address rather than the LAN/network one the dev
  server also prints. Mention the network address only when I need to reach it
  from another device.
- Same rule for non-local URLs worth clicking — a deploy, a PR, a dashboard.
  Print the whole `https://…`, never a bare domain or a description of where
  to find it.

## Keep names consistent across repos, skills, files and folders

When a repo, skill, script, output file or folder names the same thing, use
the same name for all of them. Don't ask first: rename to match and mention
it in the summary.

```
yes:  skill /project-review → skills/project-review/ → NOTES/project-review-2026-11-03.md
no:   skill /project-review writing NOTES/code-review-2026-11-03.md
```

- When something gets renamed, carry the new name through everything
  derived from it (folders, scripts, cache paths, output files, README
  lines) in the same change.
- Follow the existing separator style of the thing being matched (`-` vs
  `_`) unless a tool forbids it, and say so if one does.
