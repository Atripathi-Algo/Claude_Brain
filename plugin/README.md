# claude-brain-memory-init (optional)

A tiny Claude Code plugin with one `SessionStart` hook. If the current project has no `memory/` folder under `~/.claude/projects/<project>/`, it creates the folder and a one-line `MEMORY.md`. It never overwrites, deletes or reads anything, and does not enable code graphs or any other tooling.

Try it for one session: `claude --plugin-dir ./plugin`
Needs Node.js (already required by Claude Code installs via npm).
