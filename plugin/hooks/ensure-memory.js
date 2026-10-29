#!/usr/bin/env node
// SessionStart hook: create <claude home>/projects/<encoded cwd>/memory/ and an empty MEMORY.md if missing.
// Never overwrites or deletes anything, makes no network calls, prints nothing, always exits 0.
const fs = require("fs");
const os = require("os");
const path = require("path");

function main(input) {
  let cwd = process.cwd();
  try { const j = JSON.parse(input || "{}"); if (typeof j.cwd === "string" && j.cwd) cwd = j.cwd; } catch (_) { /* use process cwd */ }
  const home = process.env.CLAUDE_CONFIG_DIR || path.join(os.homedir(), ".claude");
  const encoded = cwd.replace(/[^A-Za-z0-9]/g, "-"); // same encoding Claude Code uses for project folders
  const mem = path.join(home, "projects", encoded, "memory");
  fs.mkdirSync(mem, { recursive: true });
  const index = path.join(mem, "MEMORY.md");
  try { fs.writeFileSync(index, "# Memory Index\n", { flag: "wx" }); } catch (e) { if (e.code !== "EEXIST") throw e; }
}

let data = "";
process.stdin.on("data", (c) => (data += c));
process.stdin.on("end", () => { try { main(data); } catch (_) { /* never block a session */ } process.exit(0); });
process.stdin.on("error", () => process.exit(0));
if (process.stdin.isTTY) { try { main(""); } catch (_) {} process.exit(0); }
