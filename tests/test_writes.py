import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from claude_brain import config
from claude_brain.api import create_app


@pytest.fixture
def rw(monkeypatch):
    real = config.load
    monkeypatch.setattr(config, "load", lambda: {**real(), "read_only": False})


@pytest.fixture
def client(brain):
    app = create_app(brain, auto_scan=False)
    app.state.svc.refresh(scan_transcripts=False)
    return TestClient(app), brain, app


def nid(brain, label):
    return next(k for k, v in brain.nodes.items() if v["label"] == label)


def snapshot(home):
    return {str(p): p.read_bytes() for p in home.rglob("*") if p.is_file()}


def test_read_only_default_blocks_every_write(client, home):
    c, brain, _ = client
    before = snapshot(home)
    n = nid(brain, "beta")
    for method, url, body in [
        ("post", "/api/note/" + n, {"content": "x", "base_hash": "h"}),
        ("post", "/api/notes/create", {"project": "proj:C--proj-a", "name": "n"}),
        ("post", "/api/notes/merge", {"ids": [n, nid(brain, "alpha")], "base_hashes": {}}),
        ("post", "/api/notes/trash", {"id": n, "base_hash": "h"}),
        ("post", "/api/index", {"project": "proj:C--proj-a", "action": "remove", "file": "alpha.md"}),
        ("post", "/api/undo", {}),
    ]:
        assert getattr(c, method)(url, json=body).status_code == 403, url
    assert snapshot(home) == before


def test_edit_atomic_backup_conflict_undo(client, home, rw, tmp_path):
    c, brain, _ = client
    n = nid(brain, "beta")
    info = c.get("/api/note-raw/" + n).json()
    new = info["text"] + "\nadded line\n"
    prev = c.post("/api/note-preview/" + n, json={"content": new}).json()
    assert "+added line" in prev["diff"]
    stale = c.post("/api/note/" + n, json={"content": new, "base_hash": "0" * 64})
    assert stale.status_code == 409
    r = c.post("/api/note/" + n, json={"content": new, "base_hash": info["hash"]})
    assert r.status_code == 200, r.text
    path = brain.nodes[n]["path"]
    assert "added line" in open(path, encoding="utf-8").read()
    assert not list(home.rglob("*.brain-tmp"))
    assert list((tmp_path / "trash").glob("*/*beta.md"))  # backup exists
    assert c.get("/api/history").json()[0]["desc"] == "Edit beta.md"
    assert c.post("/api/undo").status_code == 200
    assert "added line" not in open(path, encoding="utf-8").read()


def test_allow_list_and_secrets(client, home, rw, tmp_path):
    c, brain, app = client
    w = app.state.writer
    outside = tmp_path / "evil.md"
    outside.write_text("x")
    from claude_brain.writes import WriteError
    with pytest.raises(WriteError):
        w.allowed(outside)
    with pytest.raises(WriteError):
        w.allowed(home / "projects" / "C--proj-a" / "s1.jsonl")
    a = nid(brain, "alpha")  # contains password=... and sk-... in the fixture
    assert c.get("/api/note-raw/" + a).status_code == 422
    assert c.post("/api/note/" + nid(brain, "beta"), json={"content": "k sk-abcdefghijklmnopqrstuvwx", "base_hash": "x"}).status_code in (409, 422)


def test_create_and_index_consistency(client, home, rw):
    c, brain, _ = client
    r = c.post("/api/notes/create", json={"project": "proj:C--proj-a", "name": "New Idea", "type": "reference",
                                           "description": "a\nmultiline  desc", "body": "hello"})
    assert r.status_code == 200, r.text
    mem = home / "projects" / "C--proj-a" / "memory"
    assert (mem / "new-idea.md").exists()
    assert "- [new-idea](new-idea.md) — a multiline desc" in (mem / "MEMORY.md").read_text(encoding="utf-8").replace("\r\n", "\n")
    assert c.post("/api/notes/create", json={"project": "proj:C--proj-a", "name": "New Idea"}).status_code == 409
    c.post("/api/undo")
    assert not (mem / "new-idea.md").exists()
    assert "new-idea" not in (mem / "MEMORY.md").read_text(encoding="utf-8")


def test_merge_rewrites_links_trashes_and_undoes(client, home, rw):
    c, brain, _ = client
    mem = home / "projects" / "C--proj-a" / "memory"
    (mem / "gamma.md").write_text("---\nname: gamma\ntype: project\n---\nLinks [[beta]] and [[beta|b]].\n", encoding="utf-8")
    (mem / "MEMORY.md").write_text("- [Beta](beta.md) — b\n- [Gamma](gamma.md) — g\n", encoding="utf-8")
    c.app.state.svc.refresh(scan_transcripts=False)
    b, g = nid(brain, "beta"), nid(brain, "gamma")
    h = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
    hashes = {b: h(brain.nodes[b]["path"]), g: h(brain.nodes[g]["path"])}
    before = snapshot(home)
    r = c.post("/api/notes/merge", json={"ids": [g, b], "base_hashes": hashes})
    assert r.status_code == 200, r.text
    assert not (mem / "beta.md").exists()
    merged = (mem / "gamma.md").read_text(encoding="utf-8")
    assert "Merged from beta" in merged and "[[beta" not in merged
    assert "beta.md" not in (mem / "MEMORY.md").read_text(encoding="utf-8")
    assert c.post("/api/undo").status_code == 200
    after = snapshot(home)
    assert {k: v for k, v in after.items() if not k.endswith(".brain-tmp")} == before


def test_undo_refuses_after_external_change(client, home, rw):
    c, brain, _ = client
    n = nid(brain, "beta")
    info = c.get("/api/note-raw/" + n).json()
    assert c.post("/api/note/" + n, json={"content": info["text"] + "x\n", "base_hash": info["hash"]}).status_code == 200
    with open(brain.nodes[n]["path"], "a", encoding="utf-8") as f:
        f.write("edited elsewhere\n")
    assert c.post("/api/undo").status_code == 409
    assert "edited elsewhere" in open(brain.nodes[n]["path"], encoding="utf-8").read()


def test_settings_put_whitelist(client, monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(config, "APP_DIR", tmp_path)
    c, _, _ = client
    assert c.put("/api/settings", json={"read_only": False}).json()["read_only"] is False
    assert c.put("/api/settings", json={"claude_home": "C:/x"}).status_code == 400
    assert c.put("/api/settings", json={"read_only": "no"}).status_code == 400
    assert json.loads((tmp_path / "config.json").read_text())["read_only"] is False
