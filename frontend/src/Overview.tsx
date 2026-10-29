import { useEffect, useState } from "react";

const j = (u: string) => fetch(u).then((r) => r.json());
const fmt = (n: number) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `${(n / 1e6).toFixed(1)}M` : n >= 1e3 ? `${(n / 1e3).toFixed(1)}k` : String(n));
const ISSUE: Record<string, string> = { oversized: "oversized notes", ghost: "dangling [[links]]", orphan: "notes missing from the index", dead_entry: "dead index lines",
  malformed_frontmatter: "malformed front-matter", duplicate_candidate: "possible duplicates", stale_ref: "stale file references", index_over_cap: "index over the load cap", no_frontmatter: "notes without front-matter" };

function Card({ title, value, sub }: { title: string; value: React.ReactNode; sub?: string }) {
  return <div className="stat"><div className="muted small">{title}</div><div className="big">{value}</div>{sub && <div className="muted small">{sub}</div>}</div>;
}

export default function Overview({ tick, onOpen, onShowTemporary }: { tick: number; onOpen: (id: string) => void; onShowTemporary: () => void }) {
  const [o, setO] = useState<any>(null);
  useEffect(() => { j("/api/overview").then(setO).catch(() => {}); }, [tick]);
  if (!o) return <div className="empty">Auditing…</div>;
  const p = o.projects, n = o.notes;
  const issueTotal = Object.values(o.issues as Record<string, number>).reduce((a, b) => a + b, 0);
  return (
    <div className="overview">
      <h2>What Claude knows about your projects</h2>
      <div className="stats">
        <Card title="Projects with notes" value={p.with_notes} sub={`of ${p.real} real projects (${p.empty} have none)`} />
        <Card title="Recently active" value={p.active} sub="projects with token usage in transcripts" />
        <Card title="Notes" value={n.total} sub={`~${fmt(n.tokens_est)} tokens (estimate)`} />
        <Card title="Never read" value={n.never_read} sub={n.total ? `${Math.round((n.never_read / n.total) * 100)}% of notes: candidates to prune or rewrite` : ""} />
        <Card title="Issues" value={issueTotal} sub="see Health to fix" />
        <Card title={`Tokens, last ${o.tokens_last_days.days} days`} value={fmt(o.tokens_last_days.total)} sub="input + cache-write + output (excludes cache reads)" />
      </div>
      {p.temporary > 0 && (
        <p className="notice-inline">{p.temporary} of {p.total} project folders are temporary scratch folders (created under your system temp directory). They are hidden by default.{" "}
          <button className="link" onClick={onShowTemporary}>Show them</button></p>
      )}
      <div className="two">
        <section>
          <h3>Notes never read in a session</h3>
          {o.never_read.length === 0 ? <p className="muted">Every note has been read at least once.</p> : (
            <ul className="plain">{o.never_read.map((x: any) => (
              <li key={x.id}><button className="link" onClick={() => onOpen(x.id)}>{x.label}</button> <span className="muted small">{x.project} · ~{x.tokens_est} tok</span></li>
            ))}</ul>
          )}
          <p className="muted small">{o.note}</p>
        </section>
        <section>
          <h3>Most recently active projects</h3>
          <ul className="plain">{o.most_active.map((x: any) => (
            <li key={x.id}><button className="link" onClick={() => onOpen(x.id)}>{x.label}</button> <span className="muted small">{x.last_active} · {x.sessions} session file(s)</span></li>
          ))}</ul>
          <h3>Issues</h3>
          {issueTotal === 0 ? <p className="muted">None found.</p> : (
            <ul className="plain">{Object.entries(o.issues as Record<string, number>).map(([k, v]) => <li key={k}><b>{v}</b> {ISSUE[k] ?? k}</li>)}</ul>
          )}
        </section>
      </div>
    </div>
  );
}
