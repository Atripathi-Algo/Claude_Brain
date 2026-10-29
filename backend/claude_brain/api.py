"""FastAPI app: read-only JSON API + SSE + static frontend. Localhost only."""
import asyncio
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, metrics
from .events import Service, Watcher, sse
from .graph import Brain
from .writes import WriteError, Writer

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _hostname(value):
    value = value or ""
    if value.startswith("["):
        return value.split("]")[0] + "]"
    return value.rsplit(":", 1)[0] if ":" in value else value


def create_app(brain=None, auto_scan=True, watch=None):
    app = FastAPI(title="Claude Brain", docs_url=None, redoc_url=None)
    brain = brain or Brain(discover=True)
    svc = Service(brain)
    app.state.brain, app.state.svc = brain, svc
    watcher = Watcher(svc, config.load().get("refresh_minutes", 5))
    app.state.watcher = watcher
    watch = auto_scan if watch is None else watch

    @app.on_event("startup")
    def _startup():
        if auto_scan:
            threading.Thread(target=svc.refresh, daemon=True, name="brain-initial-scan").start()
        if watch:
            watcher.start()

    @app.on_event("shutdown")
    def _shutdown():
        watcher.shutdown()

    @app.middleware("http")
    async def host_guard(request: Request, call_next):
        if _hostname(request.headers.get("host")) not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "bad host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and _hostname(origin.split("://", 1)[-1]) not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "bad origin"}, status_code=403)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    @app.get("/api/graph")
    def graph(project: str = None, kind: str = None, type: str = None, q: str = None):
        g = brain.graph(project, kind, type, q)
        g["seq"] = svc.hub.seq
        return g

    @app.get("/api/node/{nid:path}")
    def node(nid: str):
        d = brain.node_detail(nid)
        if not d:
            raise HTTPException(404, "unknown node")
        return d

    @app.get("/api/tree")
    def tree():
        return brain.tree()

    @app.get("/api/health")
    def health():
        return brain.health()

    @app.get("/api/search")
    def search(q: str = ""):
        return metrics.search(brain, q)

    @app.get("/api/metrics/tokens")
    def tokens():
        return metrics.token_metrics(brain)

    @app.get("/api/metrics/context-cost")
    def context_cost():
        return metrics.context_cost(brain)

    @app.get("/api/metrics/extra")
    def extra():
        return {"growth": metrics.memory_growth(brain), "top_read": metrics.top_read(brain),
                "types_by_project": metrics.types_by_project(brain)}

    @app.get("/api/status")
    def status():
        return {**svc.status, "seq": svc.hub.seq, "paused": watcher.paused, "read_only": True}

    @app.get("/api/settings")
    def settings():
        return config.load()

    @app.put("/api/settings")
    def put_settings(body: dict):
        try:
            return config.update(body)
        except ValueError as e:
            raise HTTPException(400, str(e))

    # ---- Phase 3: write-back (every route is gated by the read-only setting inside Writer) ----
    writer = Writer(brain, svc)
    app.state.writer = writer

    @app.exception_handler(WriteError)
    async def _write_error(request: Request, exc: WriteError):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status)

    @app.get("/api/note-raw/{nid:path}")
    def note_raw(nid: str):
        return writer.load(nid)

    @app.post("/api/note-preview/{nid:path}")
    def note_preview(nid: str, body: dict):
        return writer.preview(nid, str(body.get("content", "")))

    @app.post("/api/note/{nid:path}")
    def note_edit(nid: str, body: dict):
        return writer.edit(nid, str(body.get("content", "")), body.get("base_hash"))

    @app.post("/api/notes/create")
    def note_create(body: dict):
        return writer.create(body.get("project", ""), body.get("name", ""), body.get("type", "project"),
                             body.get("description", ""), body.get("body", ""))

    @app.post("/api/notes/merge")
    def notes_merge(body: dict):
        return writer.merge(list(body.get("ids", [])), dict(body.get("base_hashes", {})))

    @app.post("/api/notes/trash")
    def notes_trash(body: dict):
        return writer.trash_note(body.get("id", ""), body.get("base_hash"))

    @app.post("/api/index")
    def index_edit(body: dict):
        return writer.index_edit(body.get("project", ""), body.get("action", ""), body.get("file", ""),
                                 body.get("title", ""), body.get("hook", ""))

    @app.post("/api/undo")
    def undo():
        return writer.undo()

    @app.get("/api/history")
    def history():
        return writer.history()

    @app.post("/api/rescan")
    def rescan():
        n = svc.refresh()
        return {"events": n, "seq": svc.hub.seq, "nodes": len(brain.nodes), "edges": len(brain.edges)}

    @app.post("/api/pause")
    def pause(paused: bool = True):
        watcher.paused = paused
        return {"paused": paused}

    @app.get("/api/events")
    async def events(request: Request, since: int = None):
        last = request.headers.get("last-event-id")
        if since is None and last and last.isdigit():
            since = int(last)
        q = svc.hub.subscribe()
        replay = svc.hub.since(since) if since is not None else []

        async def gen():
            try:
                if replay is None:  # client is too far behind: tell it to resync
                    yield "event: resync\ndata: {}\n\n"
                sent = since if since is not None else svc.hub.seq
                for ev in replay or []:
                    sent = ev["seq"]
                    yield sse(ev)
                yield f": connected seq={svc.hub.seq}\n\n"
                while True:
                    try:
                        ev = await asyncio.wait_for(q.get(), 15)
                    except asyncio.TimeoutError:
                        if await request.is_disconnected():
                            return
                        yield ": keepalive\n\n"
                        continue
                    if ev["seq"] > sent:
                        sent = ev["seq"]
                        yield sse(ev)
            finally:
                svc.hub.unsubscribe(q)

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    if DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            f = (DIST / path).resolve()
            if path and DIST in f.parents and f.is_file():
                return FileResponse(f)
            return FileResponse(DIST / "index.html")

    return app
