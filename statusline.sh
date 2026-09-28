#!/usr/bin/env bash
# Claude Code status line: current directory and git branch.
# Claude Code pipes session JSON on stdin; we read workspace.current_dir.

dir=$(python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("workspace",{}).get("current_dir") or d.get("cwd",""))' 2>/dev/null)
[ -z "$dir" ] && dir=$PWD

branch=$(git -C "$dir" symbolic-ref --short -q HEAD 2>/dev/null || git -C "$dir" rev-parse --short HEAD 2>/dev/null)

out=${dir/#$HOME/\~}
[ -n "$branch" ] && out="$out ($branch)"
printf '%s' "$out"
