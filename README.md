# Claude Brain

A local, **read-only** visual control panel for Claude Code memory: a 3D neuron-style graph (2D toggle and automatic fallback), a project/type/note tree, and an inspector. Free and open source; no network calls at runtime.

Honest scope: this gives **visibility**, not token savings. Token figures are `chars/4` estimates.

## Run
```
pip install fastapi uvicorn pyyaml scikit-learn watchdog
cd frontend && npm install && npm run build && cd ..
cd backend && python -m claude_brain          # http://127.0.0.1:8765
```
First scan reads all transcripts once (~40 s for ~1 GB); later scans only read appended bytes (state in `%USERPROFILE%\.claude-brain\reads.json`).

## Privacy model
- Binds to 127.0.0.1; `Host`/`Origin` headers are validated (403 otherwise).
- Write mode is OFF by default and the server refuses every write until you turn it on in Settings. With it off, nothing outside `%USERPROFILE%\.claude-brain\` is ever written.
- With it on, writes are limited to `~/.claude/projects/*/memory/*.md`; each one is atomic (temp file + rename), backed up to `%USERPROFILE%\.claude-brain	rash\` first, refused if the file changed since you loaded it, and undoable (Undo refuses if the file changed again). Deletes only ever move files to the trash. Transcripts, `settings.json`, `CLAUDE.md` and any `sales-insight-demo` folder are never touched. Notes containing secret-like text are not editable in the UI.
- Secrets (keys, tokens, `password=`, private keys) are redacted in API output; Markdown is sanitised with DOMPurify.

## How refresh works
A watchdog observer watches `~/.claude/projects` and `CLAUDE.md`. Note edits are debounced (0.5 s), transcript appends are throttled (8 s), and a full reconcile runs every 5 min plus the Rescan button. Each refresh diffs the graph and pushes deltas (`node_upsert`, `node_delete`, `edge_upsert`, `edge_delete`, `metrics_changed`, `health_changed`) over SSE at `/api/events` with a monotonic sequence number. The client resyncs from `/api/graph` on a gap or reconnect, keeps existing nodes pinned while new ones settle, and shows Live / Reconnecting / Paused.

## Status
Phase 1 (scanner, graph, 3D/2D Brain, Tree, inspector, filters) and Phase 2 (live refresh, token charts, treemap, health view, FTS5 search at `/api/search`). Phase 3 (opt-in write-back: edit with live diff, create, merge, trash, index add/remove, undo). Phase 4: optional `plugin/` (SessionStart hook that only creates a missing `memory/` + `MEMORY.md`; see `plugin/README.md`). Not yet: "mark stale" action, editing settings other than write mode.
Known limits: project label comes from the transcript `cwd`; inferred edges are TF-IDF similarity and same-session co-reads; token usage is read from transcript `usage` records (de-duplicated per message id, not independently verified against billing); memory growth uses file mtime.

## Tests
`python -m pytest tests` and `cd frontend && npx vitest run`.
