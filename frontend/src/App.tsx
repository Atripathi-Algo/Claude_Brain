import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { rescan } from "./api";
import { useLiveGraph } from "./live";
import Health from "./Health";
import { call, CreateDialog, SettingsDialog } from "./WritePanel";
import { applyFilters, defaultFilters, TYPE_COLOR, webglOk, type Filters } from "./model";
import Inspector from "./Inspector";
import TreeView from "./TreeView";
import Graph2D from "./Graph2D";

const Graph3D = lazy(() => import("./Graph3D"));
const Charts = lazy(() => import("./Charts"));
const reduceMotion = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;
const NODE_CAP_3D = 3000;
const KINDS = ["project", "memory", "index", "claude_md", "ghost"];
const TYPES = ["user", "feedback", "project", "reference"];

export default function App() {
  const { g, state: live, status, updated, flares, metricsTick, healthTick, paused, togglePause } = useLiveGraph();
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);
  const loading = busy || !!status?.scanning;
  const [view, setView] = useState<"brain" | "tree" | "charts" | "health">("brain");
  const [mode, setMode] = useState<"3d" | "2d">("3d");
  const [notice, setNotice] = useState("");
  const [f, setF] = useState<Filters>(defaultFilters());
  const [selected, setSelected] = useState<string | null>(null);
  const [hover, setHover] = useState<string | null>(null);
  const [focusTick, setFocusTick] = useState(0);
  const [theme, setTheme] = useState<"dark" | "light">(() => (matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark"));
  const [settings, setSettings] = useState<any>({ read_only: true });
  const [dlg, setDlg] = useState<null | "settings" | { create: { name?: string; project?: string } }>(null);
  const [toast, setToast] = useState("");
  const [lastOp, setLastOp] = useState("");
  const [version, setVersion] = useState(0);
  const writeOn = !settings.read_only;
  const loadSettings = useCallback(() => { fetch("/api/settings").then((r) => r.json()).then(setSettings).catch(() => {}); }, []);
  const loadHistory = useCallback(() => { fetch("/api/history").then((r) => r.json()).then((h) => setLastOp(h[0]?.desc ?? "")).catch(() => {}); }, []);
  useEffect(() => { loadSettings(); }, [loadSettings]);
  useEffect(() => { if (writeOn) loadHistory(); }, [writeOn, loadHistory, g.seq]);
  const wrote = useCallback((msg?: string) => { if (msg) setToast(msg + " — done. Undo is available in the header."); setVersion((v) => v + 1); loadHistory(); }, [loadHistory]);
  const undo = async () => {
    try { const r = await call("/api/undo", "POST"); setToast("Undid: " + r.undone); setVersion((v) => v + 1); loadHistory(); }
    catch (e: any) { setToast("Undo failed: " + e.message); }
  };
  useEffect(() => { if (!toast) return; const t = setTimeout(() => setToast(""), 6000); return () => clearTimeout(t); }, [toast]);
  const doRescan = useCallback(async () => {
    setBusy(true);
    try { await rescan(); setErr(""); } catch (e) { setErr(String(e)); } finally { setBusy(false); }
  }, []);
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
        <h1>Claude Brain <small>{writeOn ? "write mode" : "read-only"}</small></h1>
        <nav>
          <button className={view === "brain" ? "on" : ""} onClick={() => setView("brain")}>Brain</button>
          <button className={view === "tree" ? "on" : ""} onClick={() => setView("tree")}>Tree</button>
          <button className={view === "charts" ? "on" : ""} onClick={() => setView("charts")}>Charts</button>
          <button className={view === "health" ? "on" : ""} onClick={() => setView("health")}>Health</button>
        </nav>
        <div className="spacer" />
        <span className={"live " + live} role="status" aria-live="polite"><i />{live === "live" ? "Live" : live === "paused" ? "Paused" : "Reconnecting…"}</span>
        <span className="muted">{updated ? `updated ${updated.toLocaleTimeString()}` : ""}</span>
        {writeOn && <span className="badge" title="Write mode is ON">write mode</span>}
        {writeOn && lastOp && <button onClick={undo} title={`Undo: ${lastOp}`}>Undo</button>}
        <button onClick={() => setDlg("settings")}>Settings</button>
        <button onClick={togglePause} aria-pressed={paused}>{paused ? "Resume" : "Pause"}</button>
        <button onClick={doRescan} disabled={loading}>{loading ? "Scanning…" : "Rescan"}</button>
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
      {status?.scanning && status.total > 0 && status.done < status.total && <div className="notice" role="status">Scanning transcripts… {status.done}/{status.total} files (first run only; later scans read just new lines)</div>}
      {status?.error && <div className="notice warn" role="alert">Last refresh failed: {status.error}</div>}
      {err && <div className="notice warn" role="alert">Could not load data: {err}</div>}

      <main>
        <section className="stage">
          {view === "tree" ? (
            <TreeView selected={selected} onSelect={select} seq={g.seq} />
          ) : view === "charts" ? (
            <Suspense fallback={<div className="empty">Loading charts…</div>}><Charts tick={metricsTick + g.seq} onSelect={select} /></Suspense>
          ) : view === "health" ? (
            <Health tick={healthTick + metricsTick + version} onOpen={(id) => { setView("brain"); select(id); }} writeOn={writeOn} onWrote={wrote}
              onCreate={(name) => setDlg({ create: { name } })} />
          ) : filtered.nodes.length === 0 ? (
            <div className="empty">{loading ? "Scanning your Claude memory…" : g.nodes.length ? "No nodes match the filters." : "No memory notes found yet. Claude writes them under ~/.claude/projects/<project>/memory/."}</div>
          ) : eff === "3d" ? (
            <Suspense fallback={<div className="empty">Loading 3D scene…</div>}>
              <Graph3D nodes={filtered.nodes} edges={filtered.edges} selected={selected} hover={hover} focusTick={focusTick} flares={flares}
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
        <Inspector id={selected} labels={labels} onSelect={select} writeOn={writeOn} nodes={g.nodes} version={version + g.seq} onWrote={wrote}
          onNew={(project) => setDlg({ create: { project } })} />
      </main>
      {toast && <div className="toast" role="status">{toast}</div>}
      {dlg === "settings" && <SettingsDialog settings={settings} onClose={() => setDlg(null)} onChange={loadSettings} />}
      {dlg && dlg !== "settings" && <CreateDialog projects={projects} initial={dlg.create} onClose={(m) => { setDlg(null); wrote(m); }} />}
    </div>
  );
}
