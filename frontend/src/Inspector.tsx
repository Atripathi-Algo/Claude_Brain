import { useEffect, useState } from "react";
import { marked } from "marked";
import DOMPurify from "dompurify";
import { getNode } from "./api";

export default function Inspector({ id, labels, onSelect }: { id: string | null; labels: Map<string, string>; onSelect: (id: string) => void }) {
  const [d, setD] = useState<any>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    setD(null); setErr("");
    if (!id) return;
    let live = true;
    getNode(id).then((x) => live && setD(x)).catch((e) => live && setErr(String(e)));
    return () => { live = false; };
  }, [id]);

  if (!id) return <aside className="inspector"><p className="muted">Select a node to inspect it. Nothing is written to your memory files; this view is read-only.</p></aside>;
  if (err) return <aside className="inspector"><p className="warn">{err}</p></aside>;
  if (!d) return <aside className="inspector"><p className="muted">Loading…</p></aside>;
  const html = d.body ? DOMPurify.sanitize(marked.parse(d.body, { async: false }) as string) : "";
  const chip = (i: string) => <button key={i} className="chip" onClick={() => onSelect(i)}>{labels.get(i) ?? i.replace(/^ghost:/, "")}</button>;
  return (
    <aside className="inspector">
      <h2>{d.label}</h2>
      <p className="muted">{d.kind}{d.kind === "memory" ? ` / ${d.type}` : ""} · ~{d.tokens_est} tokens (estimate) · read {d.read_count}×{d.last_read_at ? `, last ${new Date(d.last_read_at).toLocaleString()}` : ""}</p>
      {d.description && <p>{d.description}</p>}
      {d.flags?.length > 0 && <p>{d.flags.map((f: string) => <span key={f} className="badge">{f}</span>)}</p>}
      {d.kind === "ghost" && <p className="muted">Referenced by [[{d.label}]] but not written yet.</p>}
      {d.backlinks?.length > 0 && <><h3>Linked from</h3><div>{d.backlinks.map(chip)}</div></>}
      {d.outlinks?.length > 0 && <><h3>Links to</h3><div>{d.outlinks.map(chip)}</div></>}
      {d.related?.length > 0 && <><h3>Inferred relations</h3><div>{d.related.map((r: any) => <button key={r.id + r.kind} className="chip dashed" onClick={() => onSelect(r.id)}>{labels.get(r.id) ?? r.id} · {r.kind}</button>)}</div></>}
      {html && <div className="md" dangerouslySetInnerHTML={{ __html: html }} />}
    </aside>
  );
}
