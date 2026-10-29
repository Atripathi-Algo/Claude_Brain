import { useEffect, useState } from "react";

const j = (u: string) => fetch(u).then((r) => r.json());
const LABEL: Record<string, string> = {
  orphan: "Orphan (not listed in MEMORY.md)", dead_entry: "Dead index entry (file missing)", ghost: "Dangling [[link]] (note not written yet)",
  oversized: "Oversized note (> ~8 KB)", index_over_cap: "MEMORY.md exceeds the 200-line / 25 KB load cap", duplicate_candidate: "Possible duplicate (similarity ≥ 0.8)",
  malformed_frontmatter: "Malformed front-matter", no_frontmatter: "No front-matter", stale_ref: "Stale reference (path no longer exists)",
};

export default function Health({ tick, onOpen }: { tick: number; onOpen: (id: string) => void }) {
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
              {i.issue.includes(":") && <span className="muted small"> {i.issue.slice(i.issue.indexOf(":") + 1)}</span>}</li>
          ))}</ul>
        </details>
      ))}
      <p className="muted small">Read-only: fixes arrive in Phase 3, behind an explicit opt-in.</p>
    </div>
  );
}
