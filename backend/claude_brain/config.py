"""Config + app-data folder. The ONLY place the app writes (read-only mode, Phase 1/2)."""
import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("CLAUDE_BRAIN_DIR") or (Path.home() / ".claude-brain"))
CONFIG_PATH = APP_DIR / "config.json"

DEFAULTS = {
    "claude_home": str(Path.home() / ".claude"),
    "read_only": True,
    "refresh_minutes": 5,
    "node_cap_3d": 3000,
    "similarity_threshold": 0.6,
    "theme": "dark",
    "port": 8765,
}


def load():
    cfg = dict(DEFAULTS)
    try:
        cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    if os.environ.get("CLAUDE_BRAIN_HOME"):  # test/demo override: point at a synthetic claude home
        cfg["claude_home"] = os.environ["CLAUDE_BRAIN_HOME"]
    return cfg


def save(cfg):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


EDITABLE = {"read_only": bool, "refresh_minutes": int, "node_cap_3d": int, "similarity_threshold": float, "theme": str}


def update(partial):
    """Persist only whitelisted, correctly-typed keys (never claude_home or the env override)."""
    try:
        cur = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cur = {}
    for k, v in partial.items():
        t = EDITABLE.get(k)
        if t is None or isinstance(v, bool) != (t is bool) or not isinstance(v, (t, int) if t is float else t):
            raise ValueError(f"invalid setting: {k}")
        cur[k] = v
    save(cur)
    return load()
