import json

from fastapi.testclient import TestClient

from claude_brain.api import create_app
from claude_brain.parsers import parse_index, parse_note
from claude_brain.redact import redact


def test_note_parsing(brain):
    n = {v["label"]: v for v in brain.nodes.values()}
    assert n["alpha"]["type"] == "project" and n["beta"]["type"] == "feedback"
    assert any("malformed_frontmatter" in v["flags"] for v in brain.nodes.values())


def test_index_and_flags(brain):
    idx = next(v for v in brain.nodes.values() if v["kind"] == "index")
    assert "dead_entry:gone.md" in idx["flags"]
    assert any(v["label"] == "beta" and "orphan" in v["flags"] for v in brain.nodes.values())
    assert parse_index("- [A](a.md) — h\r\n".replace("\r", ""))[0][0]["file"] == "a.md"


def test_links_ghost(brain):
    assert "ghost:future-note" in brain.nodes
    kinds = {(e["kind"], e["dst"]) for e in brain.edges}
    assert ("link", "ghost:future-note") in kinds


def test_reads_incremental(brain, home):
    a = next(v for v in brain.nodes.values() if v["label"] == "alpha")
    assert a["read_count"] == 1
    t = home / "projects" / "C--proj-a" / "s1.jsonl"
    with open(t, "a", encoding="utf-8") as f:
        f.write(json.dumps({"type": "assistant", "sessionId": "s2", "timestamp": "2026-10-02T00:00:00Z", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": a["path"]}}]}}) + "\n")
        f.write('{"half written')  # no newline: must be retried, not parsed
    brain.rebuild()
    assert next(v for v in brain.nodes.values() if v["label"] == "alpha")["read_count"] == 2


def test_stale_ref(brain):
    assert any(i["issue"].startswith("stale_ref:") for i in brain.health())


def test_redaction(brain):
    c = TestClient(create_app(brain, auto_scan=False))
    nid = next(k for k, v in brain.nodes.items() if v["label"] == "alpha")
    body = c.get("/api/node/" + nid).json()["body"]
    assert "hunter2" not in body and "sk-abcdef" not in body and "[REDACTED]" in body
    assert "-----BEGIN RSA PRIVATE KEY-----\nabc" not in redact("-----BEGIN RSA PRIVATE KEY-----\nabc\n-----END RSA PRIVATE KEY-----")


def test_host_and_origin_guard(brain):
    c = TestClient(create_app(brain, auto_scan=False))
    assert c.get("/api/graph", headers={"host": "evil.example.com"}).status_code == 403
    assert c.get("/api/graph", headers={"host": "127.0.0.1:8765", "origin": "http://evil.com"}).status_code == 403
    assert c.get("/api/graph", headers={"host": "127.0.0.1:8765"}).status_code == 200


def test_read_only_no_writes_in_home(home, tmp_path):
    from claude_brain.graph import Brain
    before = {p: p.stat().st_mtime_ns for p in home.rglob("*") if p.is_file()}
    Brain(home=home, state_path=tmp_path / "s.json").rebuild()
    after = {p: p.stat().st_mtime_ns for p in home.rglob("*") if p.is_file()}
    assert before == after and set(before) == set(after)
