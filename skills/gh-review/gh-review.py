#!/usr/bin/env python3
"""Inventory a GitHub account's repos, with a local cache.

Subcommands:
  scan [--owner O] [--refresh]   Refresh the cache. A repo is only re-fetched
                                 when its pushedAt/updatedAt changed since the
                                 last scan (or --refresh). Prints JSON listing
                                 the repos that still need a precis, with the
                                 description and README excerpt to write it from.
  set-precis FILE                FILE is JSON {"repo-name": "precis", ...};
                                 stores each precis in the cache.
  report [--owner O]             Print the markdown report from the cache.

Cache: ${XDG_CACHE_HOME:-~/.cache}/gh-review/<owner>.json
Needs: gh (authenticated), python3.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

DEFAULT_OWNER = "cshirky"
LIST_FIELDS = ("name,description,pushedAt,updatedAt,homepageUrl,isPrivate,"
               "isFork,isArchived,isEmpty,defaultBranchRef,url")
README_CHARS = 1500


def cache_path(owner):
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, "gh-review", f"{owner}.json")


def load_cache(owner):
    try:
        with open(cache_path(owner)) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"repos": {}}


def save_cache(owner, cache):
    path = cache_path(owner)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(cache, f, indent=1, sort_keys=True)
    os.replace(tmp, path)


class FetchError(Exception):
    """A gh call failed for a reason other than "not found"."""


def gh(*args, tries=3):
    """Run gh and return parsed JSON. Returns None only for a genuine 404
    (no Pages site, no README...). Any other failure - rate limit, network,
    server error - is retried, then raised as FetchError so the caller never
    caches a half-fetched repo as if it were real data."""
    err = ""
    for attempt in range(tries):
        r = subprocess.run(["gh", *args], capture_output=True, text=True)
        if r.returncode == 0:
            try:
                return json.loads(r.stdout) if r.stdout.strip() else None
            except json.JSONDecodeError:
                err = "unparseable JSON"
        elif "HTTP 404" in r.stderr:
            return None
        else:
            err = r.stderr.strip().splitlines()[-1] if r.stderr.strip() else f"exit {r.returncode}"
        time.sleep(2 ** attempt * 2)
    raise FetchError(f"gh {' '.join(args)}: {err}")


def file_text(full, path):
    data = gh("api", f"repos/{full}/contents/{path}")
    if not isinstance(data, dict) or "content" not in data:
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", "replace")
    except Exception:
        return None


def detect_hosting(full, meta, paths, pages):
    """Return {"github_pages": ..., "other": [...], "local": [...]}."""
    owner = full.split("/")[0].lower()
    names = {p.rsplit("/", 1)[-1] for p in paths}
    top = set(p for p in paths if "/" not in p)
    home = (meta.get("homepageUrl") or "").lower()
    out = {"github_pages": None, "other": [], "local": []}

    if pages:
        out["github_pages"] = pages.get("html_url")
    elif f"{owner}.github.io" in home:
        out["github_pages"] = meta.get("homepageUrl")

    other = out["other"]
    if "vercel.json" in top or any(p.startswith(".vercel/") for p in paths) \
            or "vercel.app" in home:
        other.append("Vercel")
    if "netlify.toml" in top or "netlify.app" in home:
        other.append("Netlify")
    if any(p.startswith(".do/") for p in paths) or "ondigitalocean.app" in home:
        other.append("DigitalOcean")
    if "fly.toml" in top:
        other.append("Fly.io")
    if "render.yaml" in top:
        other.append("Render")
    if "Procfile" in top:
        other.append("Heroku-style (Procfile)")
    if "wrangler.toml" in top or "wrangler.json" in top or "pages.dev" in home:
        other.append("Cloudflare")
    if "firebase.json" in top:
        other.append("Firebase")
    if "app.yaml" in top:
        other.append("Google App Engine")
    if "Dockerfile" in top or "docker-compose.yml" in top:
        other.append("Docker (self-hosted/any)")
    if home and not out["github_pages"] and not other:
        other.append(f"homepage: {meta.get('homepageUrl')}")

    # Deployments recorded on GitHub (Vercel/Netlify bots create these).
    deps = gh("api", f"repos/{full}/deployments?per_page=5") or []
    for d in deps if isinstance(deps, list) else []:
        creator = ((d.get("creator") or {}).get("login") or "").lower()
        for svc in ("vercel", "netlify"):
            if svc in creator and svc.capitalize() not in other:
                other.append(svc.capitalize())

    local = out["local"]
    if "package.json" in top:
        pkg = file_text(full, "package.json")
        try:
            scripts = (json.loads(pkg) or {}).get("scripts", {}) if pkg else {}
        except json.JSONDecodeError:
            scripts = {}
        for s in ("dev", "start", "serve", "preview"):
            if s in scripts:
                local.append(f"npm run {s}")
                break
    if "manage.py" in top:
        local.append("python manage.py runserver")
    if "_config.yml" in top or "Gemfile" in top and "_config.yml" in names:
        local.append("bundle exec jekyll serve")
    if any(n.endswith(".py") for n in names):
        reqs = (file_text(full, "requirements.txt") or "").lower() \
            if "requirements.txt" in top else ""
        for fw in ("streamlit", "flask", "fastapi", "dash"):
            if fw in reqs:
                local.append(f"{fw} app")
                break
    # Only shallow index.html files (root, docs/, public/...) - deep ones are
    # usually vendored examples or build output, not the project's own page.
    html = [p for p in paths if p.endswith("index.html") and p.count("/") <= 1
            and not p.startswith(("node_modules/", "."))]
    if html and not local:
        d = os.path.dirname(sorted(html, key=lambda p: p.count("/"))[0]) or "."
        local.append(f"static HTML: python3 -m http.server (from {d})")
    return out


def fetch_repo(owner, meta):
    full = f"{owner}/{meta['name']}"
    branch = (meta.get("defaultBranchRef") or {}).get("name")
    rec = {k: meta.get(k) for k in ("name", "description", "pushedAt", "updatedAt",
                                     "homepageUrl", "isPrivate", "isFork",
                                     "isArchived", "url")}
    rec["last_change"] = None
    rec["hosting"] = {"github_pages": None, "other": [], "local": []}
    rec["readme_excerpt"] = ""
    if meta.get("isEmpty") or not branch:
        rec["empty"] = True
        return rec

    commits = gh("api", f"repos/{full}/commits?sha={branch}&per_page=1")
    if isinstance(commits, list) and commits:
        sha = commits[0]["sha"]
        detail = gh("api", f"repos/{full}/commits/{sha}") or {}
        files = [f["filename"] for f in detail.get("files", [])]
        rec["last_change"] = {
            "date": commits[0]["commit"]["committer"]["date"],
            "file": files[0] if files else None,
            "other_files": max(len(files) - 1, 0),
            "message": commits[0]["commit"]["message"].splitlines()[0],
        }

    tree = gh("api", f"repos/{full}/git/trees/{branch}?recursive=1") or {}
    paths = [t["path"] for t in tree.get("tree", []) if t.get("type") == "blob"]
    pages = gh("api", f"repos/{full}/pages")
    rec["hosting"] = detect_hosting(full, meta, paths, pages)

    readme = gh("api", f"repos/{full}/readme")
    text = ""
    if isinstance(readme, dict) and "content" in readme:
        text = base64.b64decode(readme["content"]).decode("utf-8", "replace")
    if len(text.strip()) < 200 and "CLAUDE.md" in paths:
        # Many recent repos document themselves in CLAUDE.md, not a README.
        text = (text + "\n\n[from CLAUDE.md]\n" + (file_text(full, "CLAUDE.md") or "")).strip()
    if not text.strip() and "index.html" in paths:
        m = re.search(r"<title>([^<]*)", file_text(full, "index.html") or "", re.I)
        if m:
            text = f"[no README; index.html <title>: {m.group(1).strip()}]"
    rec["readme_excerpt"] = text[:README_CHARS]
    # Top-level names, for repos with no prose at all.
    rec["top_level"] = sorted({p.split("/")[0] for p in paths})[:40]
    return rec


def cmd_scan(args):
    cache = load_cache(args.owner)
    try:
        repos = gh("repo", "list", args.owner, "--limit", "1000", "--json", LIST_FIELDS)
    except FetchError as e:
        sys.exit(f"gh repo list failed - is gh installed and authenticated?\n{e}")
    old = cache["repos"]
    current = {r["name"] for r in repos}
    stale = [r for r in repos if args.refresh or r["name"] not in old
             or old[r["name"]].get("pushedAt") != r["pushedAt"]
             or old[r["name"]].get("updatedAt") != r["updatedAt"]]

    def safe_fetch(meta):
        try:
            return fetch_repo(args.owner, meta)
        except FetchError as e:
            return {"name": meta["name"], "error": str(e)}

    # Few workers: GitHub's secondary rate limit trips on bursts of requests.
    with ThreadPoolExecutor(max_workers=3) as ex:
        results = list(ex.map(safe_fetch, stale))
    failed = {r["name"]: r["error"] for r in results if "error" in r}
    fresh = [r for r in results if "error" not in r]
    # A failed repo keeps its previous cache entry (with its old pushedAt), so
    # it is retried on the next run instead of being cached half-empty.
    for rec in fresh:
        prev = old.get(rec["name"], {})
        # Keep the old precis only if the README/description didn't change.
        if prev.get("precis") and prev.get("readme_excerpt") == rec["readme_excerpt"] \
                and prev.get("description") == rec["description"]:
            rec["precis"] = prev["precis"]
        old[rec["name"]] = rec
    removed = [n for n in old if n not in current]
    for n in removed:
        del old[n]
    save_cache(args.owner, cache)

    need = [{"name": r["name"], "description": r["description"],
             "readme_excerpt": r["readme_excerpt"],
             "top_level": r.get("top_level", [])}
            for r in old.values() if not r.get("precis")]
    json.dump({"total": len(current), "rechecked": [r["name"] for r in fresh],
               "failed": failed,
               "unchanged": len(current) - len(stale), "removed": removed,
               "need_precis": need, "cache": cache_path(args.owner)},
              sys.stdout, indent=1)
    print()
    sys.stdout.flush()


def cmd_set_precis(args):
    cache = load_cache(args.owner)
    with open(args.file) as f:
        updates = json.load(f)
    for name, text in updates.items():
        if name in cache["repos"]:
            cache["repos"][name]["precis"] = text.strip()
    save_cache(args.owner, cache)
    print(f"stored {len(updates)} precis")


def hosting_cell(h):
    parts = []
    if h.get("github_pages"):
        parts.append(f"github.io: {h['github_pages']}")
    parts += h.get("other", [])
    if h.get("local"):
        parts.append("local: " + "; ".join(h["local"]))
    return "<br>".join(parts) if parts else "none detected"


def cmd_report(args):
    cache = load_cache(args.owner)
    rows = sorted(cache["repos"].values(),
                  key=lambda r: (r.get("last_change") or {}).get("date") or "",
                  reverse=True)
    print("| Repo | What it's for | Serving | Last change |")
    print("|---|---|---|---|")
    for r in rows:
        flags = [f for f, k in (("private", "isPrivate"), ("fork", "isFork"),
                                ("archived", "isArchived")) if r.get(k)]
        name = f"[{r['name']}]({r['url']})" + (f" ({', '.join(flags)})" if flags else "")
        precis = (r.get("precis") or r.get("description") or "—").replace("|", "\\|")
        lc = r.get("last_change")
        if r.get("empty"):
            last = "empty repo"
        elif lc:
            f = f"`{lc['file']}`" if lc["file"] else "(no files)"
            if lc["other_files"]:
                f += f" +{lc['other_files']} more"
            last = f"{lc['date'][:10]} {f}"
        else:
            last = "—"
        print(f"| {name} | {precis} | {hosting_cell(r['hosting'])} | {last} |")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("scan"); s.add_argument("--refresh", action="store_true")
    sp = sub.add_parser("set-precis"); sp.add_argument("file")
    rp = sub.add_parser("report")
    for x in (s, sp, rp):
        x.add_argument("--owner", default=DEFAULT_OWNER)
    args = p.parse_args()
    {"scan": cmd_scan, "set-precis": cmd_set_precis, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
