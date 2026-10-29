"""All tunables live here (defaults) and in ~/.claude-brain/config.json (overrides). Nothing else in the app
hard-codes a threshold, folder name, delay, root or limit. The app's own data folder is the only place it writes
unless write mode is on (see writes.py).

Fixed on purpose (security invariants, not settings): the server binds to 127.0.0.1 only and validates Host/Origin."""
import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("CLAUDE_BRAIN_DIR") or (Path.home() / ".claude-brain"))
CONFIG_PATH = APP_DIR / "config.json"

# key: (default, type, description)
SCHEMA = {
    "read_only": (True, bool, "Refuse every write to memory files"),
    "theme": ("dark", str, "UI theme: dark or light"),
    "port": (8765, int, "Local port"),
    "refresh_minutes": (5, int, "Full reconcile interval"),
    "debounce_md_seconds": (0.5, float, "Wait after a note changes before re-indexing"),
    "throttle_transcript_seconds": (8.0, float, "Min wait before re-reading appended transcripts"),
    "node_cap_3d": (3000, int, "Above this many visible nodes the 2D view is used"),
    "fps_floor": (25, int, "Fall back to 2D if 3D stays below this FPS"),
    "fps_floor_seconds": (6, int, "...for this many consecutive seconds"),
    "similarity_threshold": (0.6, float, "TF-IDF cosine for an inferred 'similar' edge"),
    "duplicate_threshold": (0.8, float, "TF-IDF cosine to flag a possible duplicate"),
    "similar_top_k": (3, int, "Max similar edges kept per note"),
    "co_read_max_notes": (12, int, "Ignore sessions that read more notes than this when inferring co-reads"),
    "oversized_chars": (8000, int, "Flag notes longer than this"),
    "chars_per_token": (4, int, "Token estimate = characters / this"),
    "memory_dir": ("memory", str, "Memory folder name inside each project folder"),
    "index_file": ("MEMORY.md", str, "Index file name"),
    "project_file": ("CLAUDE.md", str, "Project instructions file name"),
    "index_line_cap": (200, int, "Claude loads only this many index lines"),
    "index_byte_cap": (25600, int, "...or this many bytes, whichever is smaller"),
    "discover_projects": (True, bool, "Also list project folders on disk that Claude has no store entry for"),
    "project_roots": ([], list, "Folders to scan for projects; empty = every existing drive root plus your home"),
    "discover_depth": (3, int, "Folder levels to scan under each root"),
    "discover_limit": (500, int, "Stop after this many projects"),
    "discover_cache_seconds": (300, int, "Cache the disk scan for this long"),
    "discover_skip": (["node_modules", ".git", ".venv", "venv", "env", "__pycache__", "appdata", "$recycle.bin",
                       "system volume information", "windows", "program files", "program files (x86)",
                       "programdata", "dist", "build", ".next", "site-packages", ".cache", ".npm", ".gradle",
                       ".pub-cache", "onedrive"], list, "Folder names never entered during discovery"),
    "protected_names": (["sales-insight-demo"], list, "Paths containing these names are never written to"),
    "max_note_bytes": (204800, int, "Largest note the editor will save"),
    "undo_history": (200, int, "Operations kept for undo"),
}
DEFAULTS = {k: v[0] for k, v in SCHEMA.items()}
DEFAULTS["claude_home"] = str(Path.home() / ".claude")  # not editable through the API

_cache = {"key": None, "cfg": None}


def load():
    try:
        key = CONFIG_PATH.stat().st_mtime_ns
    except OSError:
        key = None
    key = (key, os.environ.get("CLAUDE_BRAIN_HOME"), str(CONFIG_PATH))
    if _cache["key"] == key:
        return dict(_cache["cfg"])
    cfg = {k: (list(v) if isinstance(v, list) else v) for k, v in DEFAULTS.items()}
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if os.environ.get("CLAUDE_BRAIN_HOME"):  # test/demo override: point at a synthetic claude home
        cfg["claude_home"] = os.environ["CLAUDE_BRAIN_HOME"]
    _cache.update(key=key, cfg=cfg)
    return dict(cfg)


def save(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def _valid(v, t):
    if t is bool:
        return isinstance(v, bool)
    if t is float:
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    if t is list:
        return isinstance(v, list) and all(isinstance(x, str) for x in v)
    return isinstance(v, t) and not isinstance(v, bool)


def update(partial):
    """Persist only known, correctly-typed keys (never claude_home or the env override)."""
    try:
        cur = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cur = {}
    for k, v in partial.items():
        spec = SCHEMA.get(k)
        if spec is None or not _valid(v, spec[1]):
            raise ValueError(f"invalid setting: {k}")
        cur[k] = v
    save(cur)
    return load()


def describe():
    """Settings with their defaults and descriptions, for the Settings panel."""
    cur = load()
    return [{"key": k, "value": cur[k], "default": d, "type": t.__name__, "description": desc}
            for k, (d, t, desc) in SCHEMA.items()]
