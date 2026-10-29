"""Find project folders on disk that use Claude (have a project file or a .claude folder), read-only.
These supplement ~/.claude/projects, which only lists folders Claude has actually been opened in.
Roots, depth, limits and skipped folder names all come from config."""
import os
import string
from pathlib import Path

from . import config


def default_roots():
    """Every drive root that exists, plus the home folder (works on any machine, no fixed letters)."""
    roots = [Path(f"{d}:/") for d in string.ascii_uppercase if os.path.exists(f"{d}:/")] if os.name == "nt" else [Path("/")]
    roots.append(Path.home())
    return roots


def discover(roots, max_depth, limit, skip):
    project_file = config.load()["project_file"].lower()
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
            if depth > 0 and ((project_file in names and names[project_file].is_file())
                              or (".claude" in names and names[".claude"].is_dir(follow_symlinks=False))):
                found.append(Path(d))
            if depth >= max_depth:
                continue
            for e in entries:
                try:
                    if e.is_dir(follow_symlinks=False) and e.name.lower() not in skip and e.name != ".claude":
                        stack.append((Path(e.path), depth + 1))
                except OSError:
                    continue
    return sorted(set(found))
