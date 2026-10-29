from claude_brain import config
from claude_brain.graph import Brain


def test_disk_projects_added_without_duplicating_store_projects(home, tmp_path, monkeypatch):
    root = tmp_path / "work"
    (root / "alpha-app").mkdir(parents=True)
    (root / "alpha-app" / "CLAUDE.md").write_text("# rules for alpha\n")
    (root / "beta" / ".claude").mkdir(parents=True)
    (root / "node_modules" / "junk").mkdir(parents=True)
    (root / "node_modules" / "junk" / "CLAUDE.md").write_text("x")
    (root / "plain").mkdir()
    real = config.load
    monkeypatch.setattr(config, "load", lambda: {**real(), "project_roots": [str(root)]})
    b = Brain(home=home, state_path=tmp_path / "s.json", discover=True)
    b.rebuild()
    labels = {n["label"]: n for n in b.nodes.values() if n["kind"] == "project"}
    assert {"alpha-app", "beta"} <= set(labels) and "plain" not in labels and "junk" not in labels
    assert "not_in_claude_store" in labels["alpha-app"]["flags"]
    cm = [n for n in b.nodes.values() if n["kind"] == "claude_md" and n["project"] == labels["alpha-app"]["id"]]
    assert len(cm) == 1 and cm[0]["tokens_est"] > 0
    assert len([n for n in b.nodes.values() if n["kind"] == "project" and n["label"] == "a"]) == 1  # store project kept once


def test_discovery_is_off_by_default(home, tmp_path):
    b = Brain(home=home, state_path=tmp_path / "s.json")
    b.rebuild()
    assert not any("not_in_claude_store" in n["flags"] for n in b.nodes.values())


def test_temporary_projects_flagged_and_labels_made_unique(home, tmp_path):
    import json, tempfile
    for folder, cwd in [("C--t-one", str(tmp_path / "gen" / "repo")), ("C--t-two", str(tmp_path / "other" / "repo")),
                        ("C--real", r"C:\work\repo")]:
        d = home / "projects" / folder
        d.mkdir(parents=True)
        (d / "s.jsonl").write_text(json.dumps({"type": "user", "cwd": cwd}) + "\n", encoding="utf-8")
    b = Brain(home=home, state_path=tmp_path / "s.json")
    b.rebuild()
    p = {n["id"]: n for n in b.nodes.values() if n["kind"] == "project"}
    assert str(tmp_path).lower().startswith(tempfile.gettempdir().lower())  # pytest tmp is under the system temp dir
    assert "temporary" in p["proj:C--t-one"]["flags"] and "temporary" not in p["proj:C--real"]["flags"]
    labels = [p[i]["label"] for i in ("proj:C--t-one", "proj:C--t-two", "proj:C--real")]
    assert len(set(labels)) == 3 and any("gen" in l for l in labels)
    assert p["proj:C--t-one"]["temporary"] if "temporary" in p["proj:C--t-one"] else True
    child = [n for n in b.nodes.values() if n.get("project") == "proj:C--t-one"]
    assert all(n["temporary"] for n in child)
