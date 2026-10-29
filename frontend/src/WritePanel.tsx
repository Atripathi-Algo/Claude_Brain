import { useEffect, useState } from "react";
import type { GNode } from "./api";

export async function call<T = any>(url: string, method = "GET", body?: unknown): Promise<T> {
  const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: body === undefined ? undefined : JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw Object.assign(new Error(j.detail ?? `${r.status}`), { status: r.status });
  return j;
}
const nid = (id: string) => encodeURIComponent(id).replace(/%2F/g, "/").replace(/%3A/g, ":");

function Diff({ text }: { text: string }) {
  if (!text) return <p className="muted small">No changes.</p>;
  return <pre className="diff">{text.split("\n").map((l, i) => <div key={i} className={l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : ""}>{l || " "}</div>)}</pre>;
}

/** Edit a note: raw text with a live diff preview. Saves with optimistic concurrency (base hash). */
export function Editor({ id, onDone }: { id: string; onDone: (msg?: string) => void }) {
  const [info, setInfo] = useState<{ text: string; hash: string } | null>(null);
  const [text, setText] = useState("");
  const [diff, setDiff] = useState("");
  const [err, setErr] = useState("");
  const load = () => call(`/api/note-raw/${nid(id)}`).then((i) => { setInfo(i); setText(i.text); setErr(""); }).catch((e) => setErr(e.message));
  useEffect(() => { load(); }, [id]);
  useEffect(() => {
    if (!info) return;
    const t = setTimeout(() => call(`/api/note-preview/${nid(id)}`, "POST", { content: text }).then((d) => setDiff(d.diff)).catch(() => {}), 350);
    return () => clearTimeout(t);
  }, [text, info]);
  const save = async () => {
    try { const r = await call(`/api/note/${nid(id)}`, "POST", { content: text, base_hash: info!.hash }); onDone(r.desc); }
    catch (e: any) { setErr(e.message); }
  };
  if (err && !info) return <div><p className="warn">{err}</p><button onClick={() => onDone()}>Close</button></div>;
  if (!info) return <p className="muted">Loading…</p>;
  return (
    <div className="editor">
      <textarea value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} aria-label="Note source" />
      <h3>Changes</h3><Diff text={diff} />
      {err && <p className="warn" role="alert">{err} {err.includes("changed on disk") && <button onClick={load}>Reload</button>}</p>}
      <div className="row-btn"><button className="on" onClick={save} disabled={text === info.text}>Save (backed up, undoable)</button><button onClick={() => onDone()}>Cancel</button></div>
    </div>
  );
}

export function CreateDialog({ projects, initial, onClose }: { projects: GNode[]; initial?: { name?: string; project?: string }; onClose: (msg?: string) => void }) {
  const [f, setF] = useState({ project: initial?.project ?? projects[0]?.id ?? "", name: initial?.name ?? "", type: "project", description: "", body: "" });
  const [err, setErr] = useState("");
  const go = async () => { try { const r = await call("/api/notes/create", "POST", f); onClose(r.desc); } catch (e: any) { setErr(e.message); } };
  return (
    <Modal title="New note" onClose={() => onClose()}>
      <label>Project <select value={f.project} onChange={(e) => setF({ ...f, project: e.target.value })}>{projects.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}</select></label>
      <label>Name <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></label>
      <label>Type <select value={f.type} onChange={(e) => setF({ ...f, type: e.target.value })}>{["user", "feedback", "project", "reference"].map((t) => <option key={t}>{t}</option>)}</select></label>
      <label>One-line description <input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
      <label>Body <textarea value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} /></label>
      <p className="muted small">The file is added to that project's MEMORY.md index automatically.</p>
      {err && <p className="warn" role="alert">{err}</p>}
      <button className="on" onClick={go} disabled={!f.name.trim() || !f.project}>Create</button>
    </Modal>
  );
}

export function MergeDialog({ keep, candidates, onClose }: { keep: GNode; candidates: GNode[]; onClose: (msg?: string) => void }) {
  const [other, setOther] = useState(candidates[0]?.id ?? "");
  const [err, setErr] = useState("");
  const go = async () => {
    try {
      const hashes: Record<string, string> = {};
      for (const i of [keep.id, other]) hashes[i] = (await call(`/api/note-raw/${nid(i)}`)).hash;
      const r = await call("/api/notes/merge", "POST", { ids: [keep.id, other], base_hashes: hashes });
      onClose(r.desc);
    } catch (e: any) { setErr(e.message); }
  };
  return (
    <Modal title={`Merge into “${keep.label}”`} onClose={() => onClose()}>
      <label>Merge this note into it <select value={other} onChange={(e) => setOther(e.target.value)}>{candidates.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}</select></label>
      <p className="muted small">Bodies are combined, [[links]] to the merged note are rewritten, its MEMORY.md line is removed and its file goes to the trash. One undo reverses all of it.</p>
      {err && <p className="warn" role="alert">{err}</p>}
      <button className="on" onClick={go} disabled={!other}>Merge</button>
    </Modal>
  );
}

export function SettingsDialog({ settings, onClose, onChange }: { settings: any; onClose: () => void; onChange: () => void }) {
  const [err, setErr] = useState("");
  const toggle = async () => {
    const turningOn = settings.read_only;
    if (turningOn && !window.confirm("Turn on write mode?\n\nClaude Brain will be able to edit, create, merge and trash memory notes (only inside ~/.claude/projects/*/memory). Every change is backed up to ~/.claude-brain/trash and can be undone.")) return;
    try { await call("/api/settings", "PUT", { read_only: !settings.read_only }); onChange(); } catch (e: any) { setErr(e.message); }
  };
  return (
    <Modal title="Settings" onClose={onClose}>
      <label className="switch"><input type="checkbox" checked={!settings.read_only} onChange={toggle} /> Write mode <b className={settings.read_only ? "" : "warn"}>{settings.read_only ? "OFF (read-only)" : "ON"}</b></label>
      <p className="muted small">Off by default. When off, the server refuses every write.</p>
      <dl className="kv">
        <dt>Claude home</dt><dd>{settings.claude_home}</dd>
        <dt>Reconcile every</dt><dd>{settings.refresh_minutes} min</dd>
        <dt>3D node cap</dt><dd>{settings.node_cap_3d}</dd>
        <dt>Similarity threshold</dt><dd>{settings.similarity_threshold}</dd>
      </dl>
      {err && <p className="warn" role="alert">{err}</p>}
    </Modal>
  );
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => { const k = (e: KeyboardEvent) => e.key === "Escape" && onClose(); addEventListener("keydown", k); return () => removeEventListener("keydown", k); }, [onClose]);
  return (
    <div className="modal-bg" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <div className="card-h"><h3>{title}</h3><button onClick={onClose} aria-label="Close">✕</button></div>
        {children}
      </div>
    </div>
  );
}
