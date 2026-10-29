import json

from claude_brain import metrics
from claude_brain.events import Hub, Service, sse
from fastapi.testclient import TestClient
from claude_brain.api import create_app


def _types(hub):
    return [e["type"] for e in hub.buf]


def test_edit_and_delete_produce_deltas(brain, home):
    svc = Service(brain)
    svc.refresh()
    svc.hub.buf.clear()
    mem = home / "projects" / "C--proj-a" / "memory"
    (mem / "alpha.md").write_text("---\nname: alpha\ntype: project\n---\nchanged, no links now\n", encoding="utf-8")
    svc.refresh(scan_transcripts=False)
    t = _types(svc.hub)
    assert "node_upsert" in t and "edge_delete" in t and "health_changed" in t
    svc.hub.buf.clear()
    (mem / "beta.md").unlink()
    svc.refresh(scan_transcripts=False)
    assert any(e["type"] == "node_delete" and e["data"]["id"].endswith("beta.md") for e in svc.hub.buf)
    seqs = [e["seq"] for e in svc.hub.buf]
    assert seqs == sorted(seqs) and len(set(seqs)) == len(seqs)


def test_hub_since_gap_and_sse_format():
    h = Hub(size=3)
    for i in range(5):
        h.publish("node_upsert", {"i": i})
    assert h.since(4)[0]["seq"] == 5
    assert h.since(5) == []
    assert h.since(0) is None  # buffer no longer covers the gap -> client must resync
    assert sse(h.buf[-1]).startswith("id: 5\nevent: node_upsert\ndata: ")


def test_usage_metrics_dedupe_and_incremental(brain, home):
    t = home / "projects" / "C--proj-a" / "s1.jsonl"
    u = {"input_tokens": 10, "cache_creation_input_tokens": 20, "cache_read_input_tokens": 300, "output_tokens": 5}
    line = {"type": "assistant", "timestamp": "2026-10-03T10:00:00Z", "message": {"id": "m1", "usage": u, "content": []}}
    with open(t, "a", encoding="utf-8") as f:
        f.write(json.dumps(line) + "\n" + json.dumps(line) + "\n")  # streamed duplicate
    svc = Service(brain)
    svc.refresh()
    rows = [r for r in metrics.token_metrics(brain) if r["day"] == "2026-10-03"]
    assert len(rows) == 1 and rows[0]["input"] == 10 and rows[0]["cache_read"] == 300
    svc.refresh()  # nothing new appended: totals must not change
    assert [r for r in metrics.token_metrics(brain) if r["day"] == "2026-10-03"][0]["cache_read"] == 300
    assert "metrics_changed" in _types(svc.hub)


def test_context_cost_and_search(brain):
    cc = metrics.context_cost(brain)
    assert cc and cc[0]["memory_index"] > 0 and cc[0]["user_claude_md"] > 0
    hits = metrics.search(brain, "changed")
    assert metrics.search(brain, "") == []
    assert isinstance(hits, list)
    assert any(h["label"] == "alpha" for h in metrics.search(brain, "alpha"))


def test_status_and_search_endpoints(brain):
    c = TestClient(create_app(brain, auto_scan=False))
    assert c.get("/api/status").json()["read_only"] is True
    assert c.get("/api/metrics/context-cost").status_code == 200
    assert c.get("/api/search", params={"q": "alpha"}).json()
    assert c.post("/api/pause", params={"paused": True}).json()["paused"] is True
