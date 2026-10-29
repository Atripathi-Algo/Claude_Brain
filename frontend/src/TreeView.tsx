import { useEffect, useState } from "react";
import { getTree } from "./api";

export default function TreeView({ selected, onSelect, seq, showTemporary }: { selected: string | null; onSelect: (id: string) => void; seq: number; showTemporary: boolean }) {
  const [all, setTree] = useState<any[]>([]);
  const tree = all.filter((p) => showTemporary || !p.temporary);
  const [open, setOpen] = useState<Set<string>>(new Set());
  useEffect(() => { getTree().then(setTree).catch(() => setTree([])); }, [seq]);
  const toggle = (k: string) => setOpen((o) => { const n = new Set(o); n.has(k) ? n.delete(k) : n.add(k); return n; });
  const max = Math.max(1, ...tree.map((p) => p.tokens_est));
  if (!tree.length) return <div className="empty">No projects with memory notes found yet.</div>;
  return (
    <div className="tree" role="tree">
      {tree.map((p) => (
        <div key={p.id}>
          <button className="row proj" role="treeitem" aria-expanded={open.has(p.id)} onClick={() => toggle(p.id)}>
            <span>{open.has(p.id) ? "▾" : "▸"} {p.drive ? `${p.drive}: ` : ""}{p.label}{p.no_memory && <span className="muted"> (no notes)</span>}{p.last_active && <span className="muted"> · active {p.last_active}</span>}</span>
            <span className="bar"><i style={{ width: `${(p.tokens_est / max) * 100}%` }} /></span>
            <span className="muted">~{p.tokens_est} tok</span>
          </button>
          {open.has(p.id) && p.types.map((t: any) => (
            <div key={t.type} className="indent">
              <button className="row" role="treeitem" aria-expanded={open.has(p.id + t.type)} onClick={() => toggle(p.id + t.type)}>
                <span>{open.has(p.id + t.type) ? "▾" : "▸"} {t.type} <span className="muted">({t.notes.length})</span></span>
                <span className="muted">~{t.tokens_est} tok</span>
              </button>
              {open.has(p.id + t.type) && t.notes.map((n: any) => (
                <button key={n.id} role="treeitem" className={"row note" + (selected === n.id ? " sel" : "")} onClick={() => onSelect(n.id)}>
                  <span>{n.label}{n.flags.map((f: string) => <span key={f} className="badge">{f.split(":")[0]}</span>)}</span>
                  <span className="bar"><i style={{ width: `${Math.min(100, (n.tokens_est / Math.max(1, p.tokens_est)) * 100)}%` }} /></span>
                  <span className="muted">~{n.tokens_est}</span>
                </button>
              ))}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
