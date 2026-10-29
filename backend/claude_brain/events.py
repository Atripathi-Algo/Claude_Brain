"""Live refresh: delta computation, SSE hub, debounced file watcher, periodic reconcile."""
import asyncio
import json
import threading
import time
from collections import deque
from pathlib import Path

from . import config


def diff(old_nodes, old_edges, new_nodes, new_edges):
    """-> list of (event_type, payload)."""
    out = []
    for nid, n in new_nodes.items():
        if old_nodes.get(nid) != n:
            out.append(("node_upsert", n))
    for nid in old_nodes:
        if nid not in new_nodes:
            out.append(("node_delete", {"id": nid}))
    ek = lambda e: (e["src"], e["dst"], e["kind"])
    oe, ne = {ek(e): e for e in old_edges}, {ek(e): e for e in new_edges}
    for k, e in ne.items():
        if oe.get(k) != e:
            out.append(("edge_upsert", e))
    for k, e in oe.items():
        if k not in ne:
            out.append(("edge_delete", {"src": k[0], "dst": k[1], "kind": k[2]}))
    return out


class Hub:
    """Monotonic sequence + ring buffer + fan-out to SSE subscribers (thread-safe)."""

    def __init__(self, size=1000):
        self.seq = 0
        self.buf = deque(maxlen=size)
        self.subs = []  # (loop, asyncio.Queue)
        self.lock = threading.Lock()

    def publish(self, typ, payload):
        with self.lock:
            self.seq += 1
            ev = {"seq": self.seq, "type": typ, "data": payload}
            self.buf.append(ev)
            for loop, q in list(self.subs):
                try:
                    loop.call_soon_threadsafe(q.put_nowait, ev)
                except RuntimeError:
                    pass
        return ev

    def since(self, seq):
        """Events after `seq`, or None if the buffer no longer covers the gap."""
        with self.lock:
            if seq >= self.seq:
                return []
            if not self.buf or self.buf[0]["seq"] > seq + 1:
                return None
            return [e for e in self.buf if e["seq"] > seq]

    def subscribe(self):
        q = asyncio.Queue()
        with self.lock:
            self.subs.append((asyncio.get_running_loop(), q))
        return q

    def unsubscribe(self, q):
        with self.lock:
            self.subs = [s for s in self.subs if s[1] is not q]


def sse(ev):
    return f"id: {ev['seq']}\nevent: {ev['type']}\ndata: {json.dumps(ev['data'])}\n\n"


class Service:
    """Owns refresh: rebuild -> diff -> publish. Safe to call from any thread."""

    def __init__(self, brain, hub=None):
        self.brain, self.hub = brain, hub or Hub()
        self.refresh_lock = threading.Lock()
        self.status = {"scanning": False, "done": 0, "total": 0, "last_update": None, "error": None}

    def _progress(self, done, total):
        self.status.update(done=done, total=total)

    def refresh(self, scan_transcripts=True):
        with self.refresh_lock:
            self.status["scanning"] = True
            try:
                b = self.brain
                with b.lock:
                    old_n, old_e = b.nodes, b.edges
                old_usage = json.dumps(b.state.get("usage", {}), sort_keys=True) if b.state else ""
                b.rebuild(scan_transcripts, self._progress)
                events = diff(old_n, old_e, b.nodes, b.edges)
                for typ, payload in events:
                    self.hub.publish(typ, payload)
                if events:
                    self.hub.publish("health_changed", {})
                if json.dumps(b.state.get("usage", {}), sort_keys=True) != old_usage:
                    self.hub.publish("metrics_changed", {})
                b.seq = self.hub.seq
                self.status.update(last_update=time.time(), error=None)
                return len(events)
            except Exception as e:  # never crash the server on a bad file
                self.status["error"] = repr(e)
                return 0
            finally:
                self.status["scanning"] = False


class Watcher:
    """watchdog observer + debounce thread + periodic reconcile."""

    def __init__(self, service):
        self.svc = service
        self.md_at = self.jsonl_at = 0.0
        self.stop = threading.Event()
        self.observer = None
        self.paused = False

    def _on_event(self, path):
        cfg = config.load()
        p = str(path).lower()
        now = time.time()
        if p.endswith(".md") and (cfg["memory_dir"].lower() in p or p.endswith(cfg["project_file"].lower())):
            self.md_at = now
        elif p.endswith(".jsonl"):
            self.jsonl_at = self.jsonl_at or now

    def start(self):
        from watchdog.events import FileSystemEventHandler
        from watchdog.observers import Observer
        outer = self

        class H(FileSystemEventHandler):
            def on_any_event(self, ev):
                if ev.is_directory and ev.event_type not in ("deleted", "moved"):
                    return
                outer._on_event(ev.src_path)
                dest = getattr(ev, "dest_path", "")
                if dest:
                    outer._on_event(dest)

        home = self.svc.brain.home
        self.observer = Observer()
        if (home / "projects").is_dir():
            self.observer.schedule(H(), str(home / "projects"), recursive=True)
        if home.is_dir():
            self.observer.schedule(H(), str(home), recursive=False)
        self.observer.start()
        threading.Thread(target=self._loop, daemon=True, name="brain-watch").start()

    def shutdown(self):
        self.stop.set()
        if self.observer:
            self.observer.stop()

    def _loop(self):
        last_full = time.time()
        while not self.stop.wait(0.2):
            if self.paused:
                continue
            now = time.time()
            cfg = config.load()
            if self.md_at and now - self.md_at >= cfg["debounce_md_seconds"]:
                self.md_at = 0.0
                self.svc.refresh(scan_transcripts=False)
            elif self.jsonl_at and now - self.jsonl_at >= cfg["throttle_transcript_seconds"]:
                self.jsonl_at = 0.0
                self.svc.refresh()
                last_full = time.time()
            elif now - last_full >= cfg["refresh_minutes"] * 60:
                self.svc.refresh()
                last_full = time.time()
