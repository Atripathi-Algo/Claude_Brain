import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { getGraph, rescan, type GraphData } from "./api";
import { applyFilters, defaultFilters, TYPE_COLOR, webglOk, type Filters } from "./model";
import Inspector from "./Inspector";
import TreeView from "./TreeView";
import Graph2D from "./Graph2D";

const Graph3D = lazy(() => import("./Graph3D"));
const reduceMotion = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const NODE_CAP_3D = 3000;
const KINDS = ["project", "memory", "index", "claude_md", "ghost"];
const TYPES = ["user", "feedback", "project", "reference"];

export default function App() {
  const [g, setG] = useState<GraphData>({ seq: 0, nodes: [], edges: [] });
  const [err, setErr] = useState("");
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"brain" | "tree">("brain");
  const [mode, setMode] = useState<"3d" | "2d">("3d");
  const [notice, setNotice] = useState("");
  const [f, setF] = useState<Filters>(defaultFilters());
  const [selected, setSelected] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [focusTick, setFocusTick] = useState(0);
  const [theme, setTheme] = useState<"dark" | "light">(() => (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
  const [updated, setUpdated] = useState<Date | null>(null);

  const load = useCallback(async (doRescan = false) => {
    setLoading(true);
    try {
      if (doRescan) await rescan();
      setG(await getGraph()); setErr(""); setUpdated(new Date());
    } catch (e) { setErr(String(e)); } finally { setLoading(false); }
  }, []);
  useEffect(() => { load(); }, [load]);
  useEffect(() => { document.documentElement.dataset.theme = theme; }, [theme]);
  useEffect(() => { if (!webglOk()) { setMode("2d"); setNotice("WebGL is unavailable, so the 2D view is shown."); } }, []);

  const filtered = useMemo(() => applyFilters(g, f), [g, f]);
  const labels = useMemo(() => new Map(g.nodes.map((n) => [n.id, n.label])), [g]);
  const projects = g.nodes.filter((n) => n.kind === "project");
  const tooBig = filtered.nodes.length > NODE_CAP_3D;
  const eff = tooBig ? "2d" : mode;
  const match = f.q ? g.nodes.find((n) => n.label.toLowerCase().includes(f.q.toLowerCase())) : null;

  const select = useCallback((id: string | null) => { setSelected(id); if (id) setFocusTick((t) => t + 1); }, []);
  const toggle = (key: "kinds" | "types", v: string) => setF((o) => { const s = new Set(o[key]); s.has(v) ? s.delete(v) : s.add(v); return { ...o, [key]: s }; });

  return (
    <div className="app">
      <header>
        <h1>Claude Brain <small>read-only</small></h1>
        <nav>
          <button className={view === "brain" ? "on" : ""} onClick={() => setView("brain")}>Brain</button>
          <button className={view === "tree" ? "on" : ""} onClick={() => setView("tree")}>Tree</button>
        </nav>
        <div className="spacer" />
        <span className="muted" title="Phase 1: snapshot, no live refresh yet">{updated ? `snapshot ${updated.toLocaleTimeString()}` : ""}</span>
        <button onClick={() => load(true)} disabled={loading}>{loading ? "Scanning…" : "Rescan"}</button>
        <button onClick={() => setTheme(theme === "dark" ? "light" : "dark")} aria-label="Toggle theme">{theme === "dark" ? "☀" : "☾"}</button>
      </header>

      <div className="filters">
        <input placeholder="Search nodes…" value={f.q} onChange={(e) => setF({ ...f, q: e.target.value })}
          onKeyDown={(e) => { if (e.key === "Enter" && match) select(match.id); }} aria-label="Search" />
        <select value={f.project} onChange={(e) => setF({ ...f, project: e.target.value })} aria-label="Project">
          <option value="">All projects</option>
          {projects.map((p) => <option key={p.id} value={p.id}>{p.label}</option>)}
        </select>
        {KINDS.map((k) => <label key={k}><input type="checkbox" checked={f.kinds.has(k)} onChange={() => toggle("kinds", k)} />{k}</label>)}
        {TYPES.map((t) => <label key={t}><input type="checkbox" checked={f.types.has(t)} onChange={() => toggle("types", t)} /><i className="dot" style={{ background: TYPE_COLOR[t] }} />{t}</label>)}
        <label><input type="checkbox" checked={f.inferred} onChange={() => setF({ ...f, inferred: !f.inferred })} />show inferred</label>
        <label>changed in <select value={f.recentDays} onChange={(e) => setF({ ...f, recentDays: +e.target.value })}>
          <option value={0}>any time</option><option value={1}>24 h</option><option value={7}>7 days</option><option value={30}>30 days</option></select></label>
        {view === "brain" && <button onClick={() => setMode(eff === "3d" ? "2d" : "3d")} disabled={tooBig}>{eff === "3d" ? "Switch to 2D" : "Switch to 3D"}</button>}
      </div>

      {(notice || tooBig) && <div className="notice" role="status">{tooBig ? `More than ${NODE_CAP_3D} nodes, so the 2D view is shown. Filter to use 3D.` : notice}
        {notice && <button onClick={() => setNotice("")}>dismiss</button>}</div>}
      {err && <div className="notice warn" role="alert">Could not load data: {err}</div>}

      <main>
        <section className="stage">
          {view === "tree" ? (
            <TreeView selected={selected} onSelect={select} seq={g.seq} />
          ) : filtered.nodes.length === 0 ? (
            <div className="empty">{loading ? "Scanning your Claude memory…" : g.nodes.length ? "No nodes match the filters." : "No memory notes found yet. Claude writes them under ~/.claude/projects/<project>/memory/."}</div>
          ) : eff === "3d" ? (
            <Suspense fallback={<div className="empty">Loading 3D scene…</div>}>
              <Graph3D nodes={filtered.nodes} edges={filtered.edges} selected={selected} hover={hover} focusTick={focusTick}
                onSelect={select} onHover={setHover} reduceMotion={reduceMotion}
                onLowFps={() => { setMode("2d"); setNotice("Frame rate stayed below ~25 FPS, so the 2D view is shown."); }}
                onContextLost={() => { setMode("2d"); setNotice("The WebGL context was lost, so the 2D view is shown."); }} />
            </Suspense>
          ) : (
            <Graph2D nodes={filtered.nodes} edges={filtered.edges} selected={selected} focusTick={focusTick} onSelect={select} />
          )}
          {view === "brain" && filtered.nodes.length > 0 && (
            <div className="legend">
              <span><b>solid</b> explicit link</span><span><b>dashed/dim</b> inferred (similarity, co-read)</span><span><b>wireframe</b> ghost note</span>
              <span>{filtered.nodes.length} nodes · {filtered.edges.length} edges · token counts are estimates</span>
            </div>
          )}
        </section>
        <Inspector id={selected} labels={labels} onSelect={select} />
      </main>
    </div>
  );
}
