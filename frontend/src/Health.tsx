import { useEffect, useState } from "react";

const j = (u: string) => fetch(u).then((r) => r.json());
const LABEL: Record<string, string> = {
  orphan: "Orphan (not listed in MEMORY.md)", dead_entry: "Dead index entry (file missing)", ghost: "Dangling [[link]] (note not written yet)",
  oversized: "Oversized note (> ~8 KB)", index_over_cap: "MEMORY.md exceeds the 200-line / 25 KB load cap", duplicate_candidate: "Possible duplicate (similarity ≥ 0.8)",
  malformed_frontmatter: "Malformed front-matter", no_frontmatter: "No front-matter", stale_ref: "Stale reference (path no longer exists)",
};

interface HP { tick: number; onOpen: (id: string) => void; writeOn: boolean; onWrote: (msg?: string) => void; onCreate: (name: string) => void }

/** Safe, undoable fix for an issue (only offered in write mode). */
function Fix({ i, onWrote, onCreate }: { i: any; onWrote: (m?: string) => void; onCreate: (name: string) => void }) {
  const [err, setErr] = useState("");
  const kind = i.issue.split(":")[0];
  const run = async (action: "add" | "remove", project: string, file: string, title?: string) => {
    try { onWrote((await fetch("/api/index", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project, action, file, title }) }).then(async (r) => { const j = await r.json(); if (!r.ok) throw new Error(j.detail); return j; })).desc); }
    catch (e: any) { setErr(e.message); }
  };
  const folder = i.node.replace(/^(mem|idx):/, "").split("/")[0];
  const file = i.node.split("/").pop();
  return (
    <>
      {kind === "orphan" && <button className="fix" onClick={() => run("add", "proj:" + folder, file, i.label)}>Add to index</button>}
      {kind === "dead_entry" && <button className="fix" onClick={() => run("remove", "proj:" + folder, i.issue.split(":")[1])}>Remove index line</button>}
      {kind === "ghost" && <button className="fix" onClick={() => onCreate(i.label)}>Create note</button>}
      {err && <span className="warn small"> {err}</span>}
    </>
  );
}

export default function Health({ tick, onOpen, writeOn, onWrote, onCreate }: HP) {
  const [cost, setCost] = useState<any[]>([]);
  const [issues, setIssues] = useState<any[]>([]);
  useEffect(() => {
    j("/api/metrics/context-cost").then(setCost).catch(() => {});
    j("/api/health").then(setIssues).catch(() => {});
  }, [tick]);
  const max = Math.max(1, ...cost.map((c) => c.total));
  const groups = new Map<string, any[]>();
  issues.forEach((i) => { const k = i.issue.split(":")[0]; groups.set(k, [...(groups.get(k) ?? []), i]); });
  return (
    <div className="health">
      <h2>Always-loaded context per project</h2>
      <p className="muted small">What every session starts with: your user CLAUDE.md, the project CLAUDE.md and the first 200 lines / 25 KB of MEMORY.md. Token counts are estimates (chars/4).</p>
      {cost.length === 0 && <p className="muted">No projects yet.</p>}
      {cost.map((c) => (
        <div key={c.project} className="meter">
          <div className="meter-h"><b>{c.label}</b><span className="muted">~{c.total} tokens</span></div>
          <div className="stack" style={{ width: `${(c.total / max) * 100}%` }} title="user CLAUDE.md / project CLAUDE.md / MEMORY.md">
            <i style={{ flex: c.user_claude_md, background: "#ffa86b" }} /><i style={{ flex: c.project_claude_md, background: "#5ec8ff" }} /><i style={{ flex: c.memory_index, background: "#b79cff" }} />
          </div>
          <div className="muted small">user CLAUDE.md {c.user_claude_md} · project CLAUDE.md {c.project_claude_md} · MEMORY.md {c.memory_index}
            {" "}· index at <b className={c.index_cap_pct > 80 ? "warn" : ""}>{c.index_cap_pct}%</b> of the cap ({c.index_lines} lines, {c.index_bytes} B)</div>
        </div>
      ))}
      <h2>Issues <span className="muted">({issues.length})</span></h2>
      {issues.length === 0 && <p className="muted">No issues found.</p>}
      {[...groups].map(([k, list]) => (
        <details key={k} open>
          <summary>{LABEL[k] ?? k} <span className="badge">{list.length}</span></summary>
          <ul>{list.map((i, n) => (
            <li key={n}><button className="link" onClick={() => onOpen(i.node)}>{i.label}</button>
              {i.issue.includes(":") && <span className="muted small"> {i.issue.slice(i.issue.indexOf(":") + 1)}</span>}
              {writeOn && <> <Fix i={i} onWrote={onWrote} onCreate={onCreate} /></>}</li>
          ))}</ul>
        </details>
      ))}
      <p className="muted small">{writeOn ? "Write mode is on: fix buttons make a backup and can be undone." : "Read-only. Turn on write mode in Settings to get one-click fixes."}</p>
    </div>
  );
}
