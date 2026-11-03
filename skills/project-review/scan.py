#!/usr/bin/env python3
"""Mechanical first pass for /project-review.

Usage: scan.py [PROJECT_DIR]   (default: current directory)

Prints JSON of *candidates* - unused files, unused CSS, unreferenced
functions, duplicate files and rules, data files sharing a schema, broken
Markdown links, and so on. Everything here is a heuristic based on name
matching: Claude verifies each candidate before it goes in the report.

Needs only python3. Uses `git ls-files` when the project is a git repo (so
.gitignore is respected), else walks the tree skipping the usual build and
dependency folders.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from collections import defaultdict
from collections import Counter

SKIP_DIRS = {".git", "node_modules", "dist", "build", ".next", ".vercel", ".venv",
             "venv", "__pycache__", ".cache", "coverage", ".observablehq", "out",
             ".pytest_cache", ".mypy_cache", "site-packages", "_site"}
CODE = {".py", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".rb", ".sh", ".r", ".R", ".ipynb"}
WEB = {".html", ".htm", ".css", ".scss", ".svelte", ".vue", ".erb", ".njk", ".liquid"}
DATA = {".csv", ".tsv", ".json", ".geojson", ".yaml", ".yml", ".xml", ".parquet",
        ".xlsx", ".sqlite", ".db", ".txt"}
DOCS = {".md", ".markdown", ".rst"}
TEXT = CODE | WEB | DOCS | {".csv", ".tsv", ".json", ".yaml", ".yml", ".xml", ".txt",
                            ".toml", ".cfg", ".ini", ".env.example"}
# Files that are entry points or config: nothing needs to mention them by name.
ENTRY_NAMES = {"index.html", "readme.md", "claude.md", "package.json", "package-lock.json",
               "pyproject.toml", "requirements.txt", "setup.py", "vercel.json",
               "netlify.toml", ".gitignore", "license", "license.md", "makefile",
               "dockerfile", "procfile", "tsconfig.json", "vite.config.js",
               "observablehq.config.js", "_config.yml", "gemfile", "gemfile.lock",
               "manage.py", "app.py", "main.py", "404.html", "favicon.ico", "cname",
               "robots.txt", ".nojekyll", "yarn.lock", "pnpm-lock.yaml", "uv.lock",
               "skill.md", "agents.md", "contributing.md", "changelog.md"}
# Folders whose files are picked up by convention (CI, editor, agent config).
CONVENTION_DIRS = (".github/", ".claude/", ".vscode/", ".devcontainer/")
# Framework files found by convention (file-system routing etc.), not by name.
CONVENTION_STEMS = {"page", "layout", "route", "loading", "error", "not-found",
                    "middleware", "template", "default", "global-error", "index",
                    "conftest", "__init__", "setup"}
MAX_TEXT = 2_000_000      # don't slurp text files bigger than this
NEAR_DUP_MAX = 200_000    # only compare files under this size for near-duplicates
MIN_DUP_SIZE = 64         # ignore tiny identical files (empty __init__.py etc.)


def list_files(root):
    try:
        out = subprocess.run(["git", "-C", root, "ls-files", "-co", "--exclude-standard"],
                             capture_output=True, text=True, check=True).stdout
        files = [f for f in out.splitlines() if f and os.path.isfile(os.path.join(root, f))]
        if files:
            return [f for f in files if not set(f.split("/")) & SKIP_DIRS], True
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    files = []
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x not in SKIP_DIRS]
        for n in names:
            files.append(os.path.relpath(os.path.join(d, n), root))
    return files, False


def ext(p):
    return os.path.splitext(p)[1].lower() if os.path.splitext(p)[1] else ""


def kind(p):
    e = ext(p)
    for name, group in (("code", CODE), ("web", WEB), ("data", DATA), ("docs", DOCS)):
        if e in group or os.path.splitext(p)[1] in group:
            return name
    return "other"


def read(root, p):
    path = os.path.join(root, p)
    try:
        if os.path.getsize(path) > MAX_TEXT:
            return None
        with open(path, encoding="utf-8", errors="replace") as f:
            return f.read()
    except OSError:
        return None


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
    files, in_git = list_files(root)
    sizes = {p: os.path.getsize(os.path.join(root, p)) for p in files}
    text = {p: read(root, p) for p in files if ext(p) in TEXT or os.path.basename(p).lower() in ENTRY_NAMES}
    text = {p: t for p, t in text.items() if t is not None}
    # One pass to index words per file; every "is X mentioned anywhere?" check
    # below is a set lookup instead of a regex over the whole project.
    file_tokens = {p: set(re.findall(r"[\w$.-]+", t)) | set(re.findall(r"[\w$-]+", t))
                   for p, t in text.items()}
    token_files = Counter()
    for toks in file_tokens.values():
        token_files.update(toks)
    ident_count = Counter()
    for t in text.values():
        ident_count.update(re.findall(r"[A-Za-z_$][\w$]*", t))
    out = {"root": root, "git": in_git}

    # Inventory
    inv = defaultdict(lambda: {"files": 0, "bytes": 0})
    for p in files:
        inv[kind(p)]["files"] += 1
        inv[kind(p)]["bytes"] += sizes[p]
    out["inventory"] = dict(inv)
    out["largest_files"] = sorted(([p, sizes[p]] for p in files), key=lambda x: -x[1])[:10]

    # Exact duplicate files
    by_hash = defaultdict(list)
    for p in files:
        if sizes[p] >= MIN_DUP_SIZE:
            h = hashlib.sha1()
            with open(os.path.join(root, p), "rb") as f:
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            by_hash[h.hexdigest()].append(p)
    out["duplicate_files"] = [g for g in by_hash.values() if len(g) > 1]

    # Unreferenced files: basename (or stem, for importable modules) appears in
    # no *other* text file.
    unref = []
    for p in files:
        base = os.path.basename(p)
        stem = os.path.splitext(base)[0]
        if (base.lower() in ENTRY_NAMES or base.startswith(".") or stem in CONVENTION_STEMS
                or p.startswith(CONVENTION_DIRS)
                or ".config." in base or base.endswith((".d.ts", ".test.ts", ".test.js", ".spec.ts"))):
            continue
        needles = [base]
        if ext(p) in {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".rb", ".css", ".scss"}:
            needles.append(stem)
        own = file_tokens.get(p, set())
        # Mentioned in some *other* file = appears in more files than just this one.
        if not any(token_files[n] - (1 if n in own else 0) > 0 for n in needles):
            unref.append({"file": p, "kind": kind(p), "bytes": sizes[p]})
    out["unreferenced_files"] = unref

    # Versioned / backup-looking names
    pat = re.compile(r"(_old|_bak|\.bak|_backup|_copy| copy|_v\d+|-v\d+|_orig|_new|_test\d|_draft|~)(\.|$)", re.I)
    out["versioned_names"] = [p for p in files if pat.search(os.path.basename(p))]

    # Near-duplicate text files of the same type: overlap of their non-trivial
    # lines (Jaccard), which is fast and good enough to flag copies.
    dup_set = {p for g in out["duplicate_files"] for p in g}
    line_sets = {}
    for p, t in text.items():
        if 400 < sizes[p] < NEAR_DUP_MAX and kind(p) in ("code", "web", "docs") and p not in dup_set:
            ls = {l.strip() for l in t.splitlines() if len(l.strip()) > 3}
            if len(ls) >= 10:
                line_sets[p] = ls
    by_ext = defaultdict(list)
    for p in line_sets:
        by_ext[ext(p)].append(p)
    near = []
    for group in by_ext.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                A, B = line_sets[a], line_sets[b]
                if min(len(A), len(B)) / max(len(A), len(B)) < 0.6:
                    continue
                r = len(A & B) / len(A | B)
                if r >= 0.6:
                    near.append({"a": a, "b": b, "similarity": round(r, 2)})
    out["near_duplicate_files"] = sorted(near, key=lambda x: -x["similarity"])[:40]

    # CSS: selectors defined but never used; same selector defined repeatedly;
    # identical declaration blocks under different selectors.
    css_sources = {p: t for p, t in text.items() if ext(p) in {".css", ".scss"}}
    for p, t in text.items():
        if ext(p) in {".html", ".htm", ".svelte", ".vue", ".erb"}:
            blocks = re.findall(r"<style[^>]*>(.*?)</style>", t, re.S | re.I)
            if blocks:
                css_sources[p + " <style>"] = "\n".join(blocks)
    markup_tokens = set()
    for p, toks in file_tokens.items():
        if ext(p) not in {".css", ".scss"}:
            markup_tokens |= toks
    defined = defaultdict(set)
    selector_sites = defaultdict(list)
    bodies = defaultdict(list)
    for src, css in css_sources.items():
        css_nc = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for sel, body in re.findall(r"([^{}@]+)\{([^{}]*)\}", css_nc):
            sel = " ".join(sel.split())
            if not sel or sel.startswith(("from", "to")) or re.fullmatch(r"[\d.%\s,]+", sel):
                continue
            selector_sites[sel].append(src)
            norm = ";".join(sorted(d.strip() for d in body.split(";") if d.strip()))
            if norm.count(":") >= 2:
                bodies[norm].append(f"{sel}  ({src})")
            for c in re.findall(r"\.([A-Za-z_][\w-]*)", sel):
                defined[("class", c)].add(src)
            for i in re.findall(r"#([A-Za-z_][\w-]*)", sel):
                defined[("id", i)].add(src)
    unused_css = []
    for (typ, name), srcs in sorted(defined.items()):
        if name not in markup_tokens:
            unused_css.append({"type": typ, "name": name, "defined_in": sorted(srcs)})
    out["unused_css"] = unused_css[:150]
    out["css_selector_defined_repeatedly"] = [
        {"selector": s, "sites": v} for s, v in selector_sites.items() if len(v) > 1][:60]
    out["css_identical_blocks"] = [v for v in bodies.values() if len(v) > 1][:40]

    # Functions defined at top level but whose name appears only at its definition
    defs = []
    code_text = {p: t for p, t in text.items() if kind(p) in ("code", "web")}
    for p, t in code_text.items():
        e = ext(p)
        if e == ".py":
            names = re.findall(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)", t, re.M)
            names += re.findall(r"^class\s+([A-Za-z_]\w*)", t, re.M)
        elif e in {".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".html", ".svelte", ".vue"}:
            names = re.findall(r"(?:^|\s)function\s+([A-Za-z_$][\w$]*)", t)
            names += re.findall(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>", t, re.M)
        elif e == ".rb":
            names = re.findall(r"^\s*def\s+([A-Za-z_]\w*[?!]?)", t, re.M)
        else:
            continue
        # `export default` components/handlers are loaded by the framework, not by name.
        names = set(names) - set(re.findall(r"export\s+default\s+(?:async\s+)?(?:function|class)\s+([A-Za-z_$][\w$]*)", t))
        for n in names:
            if n.startswith("__") or n in {"main", "setup", "teardown", "handler", "default"}:
                continue
            if ident_count[n] <= 1:
                defs.append({"name": n, "file": p})
    out["unreferenced_functions"] = defs[:150]

    # Same function name defined in more than one file (possible duplicated logic)
    where = defaultdict(set)
    for p, t in code_text.items():
        for n in re.findall(r"^(?:async\s+)?def\s+([A-Za-z_]\w*)|(?:^|\s)function\s+([A-Za-z_$][\w$]*)", t, re.M):
            n = n[0] or n[1]
            if n and not n.startswith("_") and n not in {"main", "init", "render", "setup", "handler"}:
                where[n].add(p)
    out["function_defined_in_several_files"] = [
        {"name": n, "files": sorted(v)} for n, v in sorted(where.items()) if len(v) > 1][:60]

    # Data files sharing a schema (same CSV header / same top-level JSON keys)
    schema = defaultdict(list)
    for p in files:
        e = ext(p)
        try:
            with open(os.path.join(root, p), encoding="utf-8", errors="replace") as f:
                if e in {".csv", ".tsv"}:
                    head = f.readline().strip()
                    if head:
                        cols = tuple(c.strip().strip('"').lower() for c in head.split("\t" if e == ".tsv" else ","))
                        if len(cols) > 1:
                            schema[("table", cols)].append(p)
                elif e == ".json" and sizes[p] < 20_000_000 and os.path.basename(p) not in {"package.json", "package-lock.json", "tsconfig.json", "vercel.json"}:
                    obj = json.load(f)
                    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
                        schema[("records", tuple(sorted(obj[0])))].append(p)
                    elif isinstance(obj, dict) and len(obj) > 1:
                        schema[("object", tuple(sorted(obj)[:30]))].append(p)
        except (OSError, ValueError, UnicodeDecodeError):
            pass
    out["data_files_sharing_schema"] = [
        {"shape": k[0], "fields": list(k[1])[:20], "files": v} for k, v in schema.items() if len(v) > 1][:30]

    # Markdown: broken relative links, and headings repeated across docs
    broken, headings = [], defaultdict(list)
    for p, t in text.items():
        if kind(p) != "docs":
            continue
        for h in re.findall(r"^#{1,4}\s+(.+?)\s*$", t, re.M):
            headings[h.strip().lower()].append(p)
        for link in re.findall(r"\]\(([^)\s#]+)", t):
            if re.match(r"[a-z]+:", link, re.I) or link.startswith("/"):
                continue
            target = os.path.normpath(os.path.join(os.path.dirname(p), link))
            if not os.path.exists(os.path.join(root, target)):
                broken.append({"in": p, "link": link})
    out["markdown_broken_links"] = broken[:60]
    generic = {"overview", "usage", "install", "installation", "setup", "notes", "status",
               "contents", "license", "todo", "requirements", "development", "deploying"}
    out["markdown_repeated_headings"] = [
        {"heading": h, "files": sorted(set(v))} for h, v in headings.items()
        if len(set(v)) > 1 and h not in generic][:40]

    # Smells worth a look
    smells = defaultdict(list)
    for p, t in text.items():
        lines = t.count("\n") + 1
        if kind(p) in ("code", "web") and lines > 800:
            smells["very_long_files"].append({"file": p, "lines": lines})
        n = len(re.findall(r"\b(TODO|FIXME|XXX|HACK)\b", t))
        if n:
            smells["todo_markers"].append({"file": p, "count": n})
        if ext(p) in {".html", ".htm"}:
            inline = len(re.findall(r'\sstyle="', t))
            if inline > 10:
                smells["many_inline_styles"].append({"file": p, "count": inline})
            scripts = re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", t, re.S | re.I)
            big = sum(s.count("\n") for s in scripts)
            if big > 300:
                smells["large_inline_scripts"].append({"file": p, "lines": big})
        if kind(p) == "code":
            hard = re.findall(r"(/Users/[\w.-]+|/home/[\w.-]+|C:\\\\Users)", t)
            if hard:
                smells["hardcoded_local_paths"].append({"file": p, "example": hard[0]})
            if re.search(r"(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][A-Za-z0-9_\-]{16,}['\"]", t, re.I):
                smells["possible_committed_secret"].append({"file": p})
            if ext(p) == ".py" and re.search(r"except\s*:\s*(pass)?\s*$", t, re.M):
                smells["bare_except"].append({"file": p})
    for p in files:
        if ext(p) in {".pyc", ".ds_store"} or os.path.basename(p) == ".DS_Store":
            smells["committed_junk_files"].append(p)
    out["smells"] = {k: v[:40] for k, v in smells.items()}
    json.dump(out, sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
