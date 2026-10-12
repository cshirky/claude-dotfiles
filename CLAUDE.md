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
