"""Find project folders on disk that use Claude (have a CLAUDE.md or a .claude folder), read-only.
These supplement ~/.claude/projects, which only lists folders Claude has actually been opened in."""
import os
from pathlib import Path

SKIP = {"node_modules", ".git", ".venv", "venv", "env", "__pycache__", "appdata", "$recycle.bin",
        "system volume information", "windows", "program files", "program files (x86)", "programdata",
        "dist", "build", ".next", "site-packages", ".cache", ".npm", ".gradle", ".pub-cache", "onedrive"}


def default_roots():
    roots = [Path(f"{d}:/") for d in "DE" if Path(f"{d}:/").exists()]
    roots.append(Path.home())
    return roots


def discover(roots, max_depth=3, limit=500):
    found = []
    for root in roots:
        stack = [(Path(root), 0)]
        while stack and len(found) < limit:
            d, depth = stack.pop()
            try:
                entries = list(os.scandir(d))
            except OSError:
                continue
            names = {e.name.lower(): e for e in entries}
            if depth > 0 and (("claude.md" in names and names["claude.md"].is_file())
                              or (".claude" in names and names[".claude"].is_dir(follow_symlinks=False))):
                found.append(Path(d))
            if depth >= max_depth:
                continue
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False) and e.name.lower() not in SKIP and e.name != ".claude":
                        stack.append((Path(e.path), depth + 1))
                except OSError:
                    continue
    return sorted(set(found))
