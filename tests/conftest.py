import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from claude_brain.graph import Brain  # noqa: E402


@pytest.fixture
def home(tmp_path):
    h = tmp_path / ".claude"
    mem = h / "projects" / "C--proj-a" / "memory"
    mem.mkdir(parents=True)
    (h / "CLAUDE.md").write_text("# rules\n", encoding="utf-8")
    (mem / "MEMORY.md").write_text(
        "- [Alpha](alpha.md) — first\r\n- [Gone](gone.md) — missing file\r\n", encoding="utf-8")
    (mem / "alpha.md").write_text(
        "---\nname: alpha\ndescription: a\nmetadata:\n  type: project\n---\nSee [[beta]] and [[future-note]].\n"
        "key password=hunter2 sk-abcdefghijklmnopqrstuvwx\n", encoding="utf-8")
    (mem / "beta.md").write_text("---\nname: beta\ntype: feedback\n---\nbody `C:/nope/missing.py`\n", encoding="utf-8")
    (mem / "bad.md").write_text("---\nname: [oops\n---\nx\n", encoding="utf-8")
    t = h / "projects" / "C--proj-a" / "s1.jsonl"
    mp = str(mem / "alpha.md").replace("\\", "\\\\")
    line = {"type": "assistant", "sessionId": "s1", "timestamp": "2026-10-01T00:00:00Z", "cwd": "C:\\proj\\a",
            "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": str(mem / "alpha.md")}}]}}
    t.write_text(json.dumps(line) + "\n", encoding="utf-8")
    return h


@pytest.fixture
def brain(home, tmp_path):
    b = Brain(home=home, state_path=tmp_path / "state.json")
    b.rebuild()
    return b
