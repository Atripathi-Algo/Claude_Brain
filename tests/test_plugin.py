import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "plugin" / "hooks" / "ensure-memory.js"
pytestmark = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")


def run(home, cwd):
    return subprocess.run(["node", str(HOOK)], input=json.dumps({"cwd": cwd}), text=True, capture_output=True,
                          env={**os.environ, "CLAUDE_CONFIG_DIR": str(home)}, timeout=20)


def test_creates_memory_and_index_only_when_missing(tmp_path):
    r = run(tmp_path, r"C:\Users\x\.claude\projects")
    assert r.returncode == 0 and r.stdout == ""
    idx = tmp_path / "projects" / "C--Users-x--claude-projects" / "memory" / "MEMORY.md"  # same encoding as Claude Code
    assert idx.read_text() == "# Memory Index\n"
    idx.write_text("- [A](a.md) - keep me\n")
    run(tmp_path, r"C:\Users\x\.claude\projects")
    assert idx.read_text() == "- [A](a.md) - keep me\n"  # never overwritten


def test_bad_input_never_fails(tmp_path):
    r = subprocess.run(["node", str(HOOK)], input="not json", text=True, capture_output=True,
                       env={**os.environ, "CLAUDE_CONFIG_DIR": str(tmp_path)}, timeout=20)
    assert r.returncode == 0
