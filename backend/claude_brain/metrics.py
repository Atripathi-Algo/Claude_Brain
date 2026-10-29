"""Derived metrics: token usage, always-loaded context cost, growth, search. All estimates are labelled as such."""
import re
import sqlite3
from pathlib import Path

from . import config, parsers
from .graph import est_tokens
from .redact import redact


def _project_label(brain, folder):
    n = brain.nodes.get("proj:" + folder)
    return n["label"] if n else folder


def token_metrics(brain):
    with brain.lock:
        rows = []
        for folder, days in brain.state.get("usage", {}).items():
            label = _project_label(brain, folder)
            for day, v in days.items():
                rows.append({"day": day, "project": label, "input": v[0], "cache_write": v[1],
                             "cache_read": v[2], "output": v[3]})
        rows.sort(key=lambda r: (r["day"], r["project"]))
        return rows


def context_cost(brain):
    """Per project: tokens loaded every session = user CLAUDE.md + project CLAUDE.md + capped MEMORY.md."""
    cfg = config.load()
    LINE_CAP, BYTE_CAP = cfg["index_line_cap"], cfg["index_byte_cap"]
    with brain.lock:
        user = brain.nodes.get("claude_md:user")
        user_tok = user["tokens_est"] if user else 0
        out = []
        for pid, p in brain.nodes.items():
            if p["kind"] != "project":
                continue
            proj_tok = 0
            if p["path"] and Path(p["path"]).is_dir():
                cm = Path(p["path"]) / cfg["project_file"]
                if cm.is_file():
                    proj_tok = est_tokens(len(parsers.read_text(cm)))
            idx = brain.indexes.get(pid)
            if not idx and not proj_tok:
                continue  # nothing project-specific is loaded; don't list every empty project
            idx_tok = lines = size = 0
            if idx:
                node = brain.nodes.get("idx:" + pid[5:])
                text = parsers.read_text(node["path"]) if node else ""
                loaded = "\n".join(text.split("\n")[:LINE_CAP]).encode("utf-8")[:BYTE_CAP]
                idx_tok, lines, size = est_tokens(len(loaded)), idx["lines"], idx["bytes"]
            pct = round(max(lines / LINE_CAP, size / BYTE_CAP) * 100, 1)
            out.append({"project": pid, "label": p["label"], "user_claude_md": user_tok, "project_claude_md": proj_tok,
                        "memory_index": idx_tok, "total": user_tok + proj_tok + idx_tok,
                        "index_lines": lines, "index_bytes": size, "index_cap_pct": pct})
        out.sort(key=lambda r: -r["total"])
        return out


def overview(brain):
    """One-screen audit: what exists, what is used, and what is worth cleaning up."""
    cfg = config.load()
    with brain.lock:
        projects = [n for n in brain.nodes.values() if n["kind"] == "project"]
        notes = [n for n in brain.nodes.values() if n["kind"] == "memory"]
        temp = [p for p in projects if "temporary" in p["flags"]]
        real = [p for p in projects if "temporary" not in p["flags"]]
        with_notes = [p for p in real if "no_memory" not in p["flags"]]
        active = [p for p in real if p.get("last_active")]
        unread = sorted((n for n in notes if not n["read_count"]), key=lambda n: -n["tokens_est"])
        label = lambda n: brain.nodes[n["project"]]["label"]
        usage = {}
        for folder, days in brain.state.get("usage", {}).items():
            for day, v in days.items():
                usage[day] = usage.get(day, 0) + v[0] + v[1] + v[3]
        recent = sorted(usage)[-30:]
        issues = {}
        for i in brain.health():
            k = i["issue"].split(":")[0]
            issues[k] = issues.get(k, 0) + 1
    return {
        "projects": {"total": len(projects), "temporary": len(temp), "real": len(real), "with_notes": len(with_notes),
                     "active": len(active), "empty": len(real) - len(with_notes),
                     "not_in_store": sum("not_in_claude_store" in p["flags"] for p in projects)},
        "notes": {"total": len(notes), "never_read": len(unread), "read": len(notes) - len(unread),
                  "tokens_est": sum(n["tokens_est"] for n in notes)},
        "never_read": [{"id": n["id"], "label": n["label"], "project": label(n), "tokens_est": n["tokens_est"]} for n in unread[:15]],
        "most_active": [{"id": p["id"], "label": p["label"], "last_active": p["last_active"], "sessions": p.get("sessions", 0)}
                        for p in sorted(active, key=lambda p: p["last_active"], reverse=True)[:8]],
        "issues": issues,
        "tokens_last_days": {"days": len(recent), "total": sum(usage[d] for d in recent)},
        "note": f"Token counts are estimates (characters / {cfg['chars_per_token']}); 'never read' means no Read of the file was found in your transcripts.",
    }


def memory_growth(brain):
    """Cumulative note count by last-modified day (file mtime; creation time is unknown)."""
    with brain.lock:
        from datetime import datetime, timezone
        days = {}
        for n in brain.nodes.values():
            if n["kind"] == "memory" and n["mtime"]:
                d = datetime.fromtimestamp(n["mtime"], timezone.utc).strftime("%Y-%m-%d")
                days[d] = days.get(d, 0) + 1
        total, out = 0, []
        for d in sorted(days):
            total += days[d]
            out.append({"day": d, "notes": total})
        return out


def top_read(brain, limit=10):
    with brain.lock:
        ns = [n for n in brain.nodes.values() if n["kind"] == "memory" and n["read_count"]]
        ns.sort(key=lambda n: -n["read_count"])
        return [{"id": n["id"], "label": n["label"], "reads": n["read_count"]} for n in ns[:limit]]


def types_by_project(brain):
    with brain.lock:
        out = {}
        for n in brain.nodes.values():
            if n["kind"] == "memory":
                p = brain.nodes[n["project"]]["label"]
                out.setdefault(p, {}).setdefault(n["type"], 0)
                out[p][n["type"]] += 1
        return out


_fts = {"key": None, "db": None}


def search(brain, q, limit=25):
    """FTS5 over note label/description/body (rebuilt when the graph changes)."""
    with brain.lock:
        key = (id(brain.notes), len(brain.notes))
        if _fts["key"] != key:
            db = sqlite3.connect(":memory:", check_same_thread=False)
            db.execute("CREATE VIRTUAL TABLE t USING fts5(id UNINDEXED, label, body)")
            for nid, note in brain.notes.items():
                db.execute("INSERT INTO t VALUES (?,?,?)", (nid, note["name"], note["description"] + "\n" + note["body"]))
            _fts.update(key=key, db=db)
        terms = re.findall(r"\w+", q)
        if not terms:
            return []
        match = " ".join('"%s"*' % t for t in terms)
        try:
            rows = _fts["db"].execute(
                "SELECT id, label, snippet(t, 2, '[', ']', '…', 12) FROM t WHERE t MATCH ? ORDER BY rank LIMIT ?",
                (match, limit)).fetchall()
        except sqlite3.Error:
            return []
        return [{"id": i, "label": l, "snippet": redact(s)} for i, l, s in rows]
