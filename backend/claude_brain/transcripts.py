"""Incremental transcript scan (tailed by byte offset): memory-file reads and token usage."""
import json
from pathlib import Path

from . import config

STATE_VERSION = 2


def _markers():
    """Byte patterns that cheaply pre-filter transcript lines mentioning the memory folder (JSON-escaped on Windows)."""
    m = config.load()["memory_dir"]
    return ("\\\\" + m + "\\\\").encode(), ("/" + m + "/").encode(), m.lower()


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


def scan(projects_dir, state, progress=None):
    """Update `state`; parse only appended complete lines.
    reads: {normpath: {count,last}}  sessions: {sid: [normpath]}
    usage: {project_folder: {day: [input, cache_write, cache_read, output]}}"""
    offsets = state.setdefault("offsets", {})
    reads = state.setdefault("reads", {})
    sessions = state.setdefault("sessions", {})
    usage = state.setdefault("usage", {})
    changed = False
    mark, mark2, mem_name = _markers()
    files = list(Path(projects_dir).glob("*/*.jsonl"))
    for i, jf in enumerate(files):
        if progress:
            progress(i, len(files))
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
        pending = {}  # message id -> (day, usage); last occurrence wins (streamed duplicates)
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
                    has_use = b'"usage"' in raw and b'"assistant"' in raw
                    has_mem = (mark in raw or mark2 in raw) and b'"tool_use"' in raw
                    if has_use or has_mem:
                        _handle(raw, reads, sessions, pending, has_mem, mem_name)
                off = fh.tell()
        except OSError:
            continue
        proj = usage.setdefault(jf.parent.name, {})
        for day, u in pending.values():
            row = proj.setdefault(day, [0, 0, 0, 0])
            row[0] += u.get("input_tokens") or 0
            row[1] += u.get("cache_creation_input_tokens") or 0
            row[2] += u.get("cache_read_input_tokens") or 0
            row[3] += u.get("output_tokens") or 0
        offsets[key] = off
        changed = True
    if progress:
        progress(len(files), len(files))
    return changed


def _handle(raw, reads, sessions, pending, has_mem, mem_name):
    try:
        o = json.loads(raw)
    except ValueError:
        return
    msg = o.get("message")
    if not isinstance(msg, dict):
        return
    ts = o.get("timestamp") or ""
    u = msg.get("usage")
    if isinstance(u, dict) and o.get("type") == "assistant" and len(ts) >= 10:
        mid = msg.get("id") or o.get("uuid") or id(o)
        pending[mid] = (ts[:10], u)
    content = msg.get("content")
    if not has_mem or not isinstance(content, list):
        return
    sid = o.get("sessionId") or "?"
    for b in content:
        if isinstance(b, dict) and b.get("type") == "tool_use" and b.get("name") == "Read":
            fp = (b.get("input") or {}).get("file_path")
            if isinstance(fp, str) and mem_name in fp.lower() and fp.lower().endswith(".md"):
                p = _norm(fp)
                r = reads.setdefault(p, {"count": 0, "last": ""})
                r["count"] += 1
                if ts > r["last"]:
                    r["last"] = ts
                lst = sessions.setdefault(sid, [])
                if p not in lst:
                    lst.append(p)
