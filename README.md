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
- Phase 1 writes only to `%USERPROFILE%\.claude-brain\`. Memory files, transcripts and settings are never modified.
- Secrets (keys, tokens, `password=`, private keys) are redacted in API output; Markdown is sanitised with DOMPurify.

## Status
Phase 1 (scanner, graph, 3D/2D Brain, Tree, inspector, filters). Not yet: live refresh/SSE, charts, health view, write-back, plugin.
Known limits: project label comes from the transcript `cwd` (falls back to folder name); inferred edges are TF-IDF similarity and same-session co-reads.

## Tests
`python -m pytest tests` and `cd frontend && npx vitest run`.
