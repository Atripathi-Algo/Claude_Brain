"""Config + app-data folder. The ONLY place the app writes (read-only mode, Phase 1/2)."""
import json
import os
from pathlib import Path

APP_DIR = Path.home() / ".claude-brain"
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
