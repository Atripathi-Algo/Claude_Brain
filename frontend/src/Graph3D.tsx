import { useEffect, useMemo, useRef, useState } from "react";
import ForceGraph3D from "react-force-graph-3d";
import * as THREE from "three";
import SpriteText from "three-spritetext";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import type { GEdge, GNode } from "./api";
import { colorOf, mergeNodes, neighbours } from "./model";

interface Props {
  nodes: GNode[]; edges: GEdge[]; selected: string | null; hover: string | null; focusTick: number;
  onSelect: (id: string | null) => void; onHover: (id: string | null) => void;
  onLowFps: () => void; onContextLost: () => void; reduceMotion: boolean;
}

export default function Graph3D(p: Props) {
  const fg = useRef<any>(null);
  const store = useRef(new Map<string, any>());
  const wrap = useRef<HTMLDivElement>(null);
  const size = useRef({ w: 800, h: 600 });
  const [dims, setDims] = useState({ w: 800, h: 600 });
  const cb = useRef(p);
  cb.current = p;

  const data = useMemo(() => {
    const ns = mergeNodes(store.current, p.nodes);
    const links = p.edges.map((e) => ({ source: e.src, target: e.dst, kind: e.kind, explicit: e.explicit, weight: e.weight }));
    return { nodes: ns, links };
  }, [p.nodes, p.edges]);

  const focus = p.hover ?? p.selected;
  const lit = useMemo(() => (focus ? neighbours(focus, p.edges) : null), [focus, p.edges]);

  // project cluster centres on a sphere
  const centres = useMemo(() => {
    const ps = [...new Set(p.nodes.map((n) => n.project).filter(Boolean))] as string[];
    const m = new Map<string, THREE.Vector3>();
    ps.forEach((id, i) => {
      const k = ps.length;
      const y = k === 1 ? 0 : 1 - (2 * (i + 0.5)) / k, r = Math.sqrt(1 - y * y), a = i * 2.399963;
      m.set(id, new THREE.Vector3(Math.cos(a) * r, y, Math.sin(a) * r).multiplyScalar(k === 1 ? 0 : 140));
    });
    return m;
  }, [p.nodes]);

  useEffect(() => {
    const g = fg.current; if (!g) return;
    g.d3Force("cluster", (alpha: number) => {
      for (const n of store.current.values()) {
        const c = n.project && centres.get(n.project); if (!c || n.fx != null) continue;
        const k = 0.08 * alpha;
        n.vx += (c.x - (n.x ?? 0)) * k; n.vy += (c.y - (n.y ?? 0)) * k; n.vz += (c.z - (n.z ?? 0)) * k;
      }
    });
    g.d3Force("link")?.distance((l: any) => (l.kind === "in_project" ? 40 : 60));
    g.d3ReheatSimulation?.();
  }, [centres, data]);

  useEffect(() => { // bloom for the neuron glow (cosmetic, failures ignored)
    const g = fg.current; if (!g) return;
    try {
      const composer = g.postProcessingComposer();
      const bloom = new UnrealBloomPass(new THREE.Vector2(size.current.w, size.current.h), 0.9, 0.6, 0.15);
      composer.addPass(bloom);
      return () => { try { composer.removePass(bloom); bloom.dispose(); } catch { /* ignore */ } };
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { // resize, context loss, FPS watchdog, disposal
    const el = wrap.current!; const canvas = () => el.querySelector("canvas");
    const ro = new ResizeObserver(([e]) => {
      size.current = { w: Math.floor(e.contentRect.width), h: Math.floor(e.contentRect.height) };
      setDims(size.current);
    });
    ro.observe(el);
    const lost = (ev: Event) => { ev.preventDefault(); cb.current.onContextLost(); };
    canvas()?.addEventListener("webglcontextlost", lost);
    let frames = 0, last = performance.now(), slow = 0, raf = 0;
    const tick = (t: number) => {
      frames++;
      if (t - last >= 1000) {
        slow = frames < 25 && !document.hidden ? slow + 1 : 0; frames = 0; last = t;
        if (slow >= 6) { cb.current.onLowFps(); return; }
      }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => {
      ro.disconnect(); cancelAnimationFrame(raf);
      canvas()?.removeEventListener("webglcontextlost", lost);
      fg.current?._destructor?.();
    };
  }, []);

  useEffect(() => { // fly to selected
    const n = p.selected && store.current.get(p.selected); if (!n || n.x == null) return;
    const d = 90, r = 1 + d / Math.hypot(n.x, n.y, n.z || 1);
    fg.current?.cameraPosition({ x: n.x * r, y: n.y * r, z: n.z * r }, n, 900);
  }, [p.focusTick]);

  const nodeObj = (n: any) => {
    const g = new THREE.Group();
    const dim = lit && !lit.has(n.id);
    const rad = n.kind === "project" ? 7 : n.kind === "ghost" ? 3.5 : 3 + Math.min(6, Math.sqrt(n.degree + n.read_count));
    const col = new THREE.Color(colorOf(n));
    const recent = n.last_read_at && Date.now() - Date.parse(n.last_read_at) < 864e5;
    const mat = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: dim ? 0.12 : n.kind === "ghost" ? 0.35 : 1, wireframe: n.kind === "ghost" });
    g.add(new THREE.Mesh(new THREE.SphereGeometry(rad, 16, 16), mat));
    if (recent && !dim && !p.reduceMotion) {
      g.add(new THREE.Mesh(new THREE.SphereGeometry(rad * 1.6, 12, 12), new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.18 })));
    }
    const showLabel = !dim && (n.id === p.selected || n.id === p.hover || n.kind === "project" || n.degree >= 3 || (lit && lit.has(n.id)));
    if (showLabel) {
      const s: any = new SpriteText(n.label, n.kind === "project" ? 5 : 3.2, "#e8ecf4");
      s.position.y = rad + 5; s.material.depthWrite = false; g.add(s);
    }
    return g;
  };

  return (
    <div ref={wrap} className="graph-wrap" data-testid="graph3d">
      <ForceGraph3D
        ref={fg}
        graphData={data}
        width={dims.w}
        height={dims.h}
        backgroundColor="rgba(0,0,0,0)"
        nodeThreeObject={nodeObj}
        nodeLabel={(n: any) => `${n.label} · ${n.kind}${n.kind === "memory" ? "/" + n.type : ""}`}
        linkColor={(l: any) => (lit && !(lit.has(l.source.id) && lit.has(l.target.id)) ? "rgba(120,130,150,0.05)" : l.kind === "in_project" ? "rgba(150,160,180,0.18)" : l.explicit ? "rgba(190,210,255,0.85)" : "rgba(160,150,200,0.35)")}
        linkWidth={(l: any) => (l.explicit && l.kind !== "in_project" ? 1.2 : 0.4)}
        linkCurvature={(l: any) => (l.kind === "in_project" ? 0 : 0.2)}
        linkDirectionalParticles={(l: any) => (p.reduceMotion || l.kind === "in_project" ? 0 : l.explicit ? 2 : 1)}
        linkDirectionalParticleWidth={1.6}
        linkDirectionalParticleSpeed={0.006}
        linkDirectionalParticleColor={() => "#9fd0ff"}
        onNodeClick={(n: any) => p.onSelect(n.id)}
        onNodeHover={(n: any) => p.onHover(n ? n.id : null)}
        onBackgroundClick={() => p.onSelect(null)}
        onNodeDragEnd={(n: any) => { n.fx = n.x; n.fy = n.y; n.fz = n.z; }}
        cooldownTicks={200}
        enableNavigationControls
      />
    </div>
  );
}
