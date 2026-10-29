"""FastAPI app: read-only JSON API + static frontend. Localhost only."""
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .graph import Brain

ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]", "testserver"}
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def create_app(brain=None, auto_scan=True):
    app = FastAPI(title="Claude Brain", docs_url=None, redoc_url=None)
    app.state.brain = brain or Brain()
    if auto_scan:
        app.state.brain.rebuild()

    @app.middleware("http")
    async def host_guard(request: Request, call_next):
        host = (request.headers.get("host") or "").rsplit(":", 1)[0] if not (request.headers.get("host") or "").startswith("[") \
            else (request.headers.get("host") or "").split("]")[0] + "]"
        if host not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "bad host"}, status_code=403)
        origin = request.headers.get("origin")
        if origin and origin.split("://", 1)[-1].rsplit(":", 1)[0] not in ALLOWED_HOSTS:
            return JSONResponse({"detail": "bad origin"}, status_code=403)
        resp = await call_next(request)
        resp.headers["X-Content-Type-Options"] = "nosniff"
        return resp

    b = lambda: app.state.brain

    @app.get("/api/graph")
    def graph(project: str = None, kind: str = None, type: str = None, q: str = None):
        return b().graph(project, kind, type, q)

    @app.get("/api/node/{nid:path}")
    def node(nid: str):
        d = b().node_detail(nid)
        if not d:
            raise HTTPException(404, "unknown node")
        return d

    @app.get("/api/tree")
    def tree():
        return b().tree()

    @app.get("/api/health")
    def health():
        return b().health()

    @app.get("/api/settings")
    def settings():
        return config.load()

    @app.post("/api/rescan")
    def rescan():
        b().rebuild()
        return {"seq": b().seq, "nodes": len(b().nodes), "edges": len(b().edges)}

    if DIST.is_dir():
        app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

        @app.get("/{path:path}")
        def spa(path: str):
            f = (DIST / path).resolve()
            if path and DIST in f.parents and f.is_file():
                return FileResponse(f)
            return FileResponse(DIST / "index.html")

    return app
