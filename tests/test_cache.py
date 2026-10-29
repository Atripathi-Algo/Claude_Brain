from fastapi.testclient import TestClient

from claude_brain import config
from claude_brain.api import create_app


def make(brain):
    app = create_app(brain, auto_scan=False)
    app.state.svc.refresh()
    return TestClient(app), app


def test_list_shows_items_and_sizes(brain):
    c, _ = make(brain)
    r = c.get("/api/cache").json()
    ids = {i["id"]: i for i in r["items"]}
    assert set(ids) == {"scan_state", "discovery", "search_index", "trash"}
    assert ids["scan_state"]["bytes"] > 0 and ids["trash"]["warning"]


def test_clear_requires_confirmation_and_known_ids(brain):
    c, _ = make(brain)
    assert c.post("/api/cache/clear", json={"ids": ["scan_state"]}).status_code == 400
    assert c.post("/api/cache/clear", json={"ids": ["scan_state"], "confirm": "yes"}).status_code == 400
    assert c.post("/api/cache/clear", json={"ids": ["../etc"], "confirm": True}).status_code == 400
    assert c.post("/api/cache/clear", json={"ids": [], "confirm": True}).status_code == 400
    assert brain.state_path.exists()  # nothing deleted by the refused calls


def test_clear_scan_state_rescans_and_keeps_everything_else(brain, home, tmp_path):
    c, app = make(brain)
    before_notes = {p.name: p.read_bytes() for p in home.rglob("*.md")}
    assert c.post("/api/cache/clear", json={"ids": ["scan_state"], "confirm": True}).json()["rescanning"] is True
    import time
    for _ in range(50):  # background rescan
        if brain.state.get("reads") and not app.state.svc.status["scanning"]:
            break
        time.sleep(0.1)
    assert brain.state["reads"]  # rebuilt from the transcript
    assert {p.name: p.read_bytes() for p in home.rglob("*.md")} == before_notes  # Claude's files untouched


def test_clear_trash_deletes_backups_only(brain, home, monkeypatch):
    real = config.load
    monkeypatch.setattr(config, "load", lambda: {**real(), "read_only": False})
    c, app = make(brain)
    nid = next(k for k, v in brain.nodes.items() if v["label"] == "beta")
    info = c.get("/api/note-raw/" + nid).json()
    assert c.post("/api/note/" + nid, json={"content": info["text"] + "x\n", "base_hash": info["hash"]}).status_code == 200
    assert app.state.writer.trash.exists()
    assert c.post("/api/cache/clear", json={"ids": ["trash"], "confirm": True}).status_code == 200
    assert not app.state.writer.trash.exists()
    assert "x" in open(brain.nodes[nid]["path"], encoding="utf-8").read()  # the edited note itself is kept
    assert c.get("/api/history").json() == []


def test_settings_schema_has_no_unlisted_defaults(brain):
    c, _ = make(brain)
    keys = {s["key"] for s in c.get("/api/settings/schema").json()}
    assert {"index_line_cap", "memory_dir", "protected_names", "project_roots", "fps_floor", "node_cap_3d"} <= keys
    assert c.put("/api/settings", json={"index_line_cap": "x"}).status_code == 400
