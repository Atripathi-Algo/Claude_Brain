"""Incremental transcript scan: memory-file reads per path (tailed by byte offset)."""
import json
from pathlib import Path

MARK = b"\\\\memory\\\\"  # JSON-escaped "\memory\" (Windows)
MARK2 = b"/memory/"


def _norm(p):
    return str(p).replace("/", "\\").lower()


def project_cwd(jsonl_dir):
    """First `cwd` found in the first transcripts of a project folder (head only)."""
    for f in sorted(Path(jsonl_dir).glob("*.jsonl"))[:3]:
        try:
            with open(f, "rb") as fh:
                for _ in range(60):
                    raw = fh.readline()
                    if not raw:
                        break
                    if b'"cwd"' in raw:
                        try:
                            c = json.loads(raw).get("cwd")
                        except ValueError:
                            continue
                        if c:
                            return c
        except OSError:
            continue
    return None


def scan(projects_dir, state):
    """Update `state` {offsets, reads, sessions}; parse only appended complete lines.
    reads: {normpath: {count, last}}  sessions: {sid: [normpath,...]}"""
    offsets = state.setdefault("offsets", {})
    reads = state.setdefault("reads", {})
    sessions = state.setdefault("sessions", {})
    changed = False
    for jf in Path(projects_dir).glob("*/*.jsonl"):
        key = str(jf)
        try:
            size = jf.stat().st_size
        except OSError:
            continue
        off = offsets.get(key, 0)
        if size < off:
            off = 0  # truncated/rotated
        if size == off:
            continue
        try:
            with open(jf, "rb") as fh:
                fh.seek(off)
                while True:
                    start = fh.tell()
                    raw = fh.readline()
                    if not raw:
                        break
                    if not raw.endswith(b"\n"):  # half-written last line: retry later
                        fh.seek(start)
                        break
                    if (MARK in raw or MARK2 in raw) and b'"tool_use"' in raw:
                        _handle(raw, reads, sessions)
                off = fh.tell()
        except OSError:
            continue
        offsets[key] = off
        changed = True
    return changed


def _handle(raw, reads, sessions):
    try:
        o = json.loads(raw)
    except ValueError:
        return
    msg = o.get("message")
    content = msg.get("content") if isinstance(msg, dict) else None
    if not isinstance(content, list):
        return
    sid = o.get("sessionId") or "?"
    ts = o.get("timestamp") or ""
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Read":
            fp = (b.get("input") or {}).get("file_path")
            if isinstance(fp, str) and "memory" in fp.lower() and fp.lower().endswith(".md"):
                p = _norm(fp)
                r = reads.setdefault(p, {"count": 0, "last": ""})
                r["count"] += 1
                if ts > r["last"]:
                    r["last"] = ts
                lst = sessions.setdefault(sid, [])
                if p not in lst:
                    lst.append(p)
