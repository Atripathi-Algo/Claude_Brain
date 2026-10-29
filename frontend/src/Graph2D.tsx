import { useEffect, useRef } from "react";
import cytoscape from "cytoscape";
// @ts-ignore no types
import fcose from "cytoscape-fcose";
import type { GEdge, GNode } from "./api";
import { colorOf } from "./model";

let registered = false;

interface Props { nodes: GNode[]; edges: GEdge[]; selected: string | null; focusTick: number; onSelect: (id: string | null) => void }

export default function Graph2D({ nodes, edges, selected, focusTick, onSelect }: Props) {
  const el = useRef<HTMLDivElement>(null);
  const cy = useRef<cytoscape.Core | null>(null);
  const sel = useRef(onSelect);
  sel.current = onSelect;

  useEffect(() => {
    if (!registered) { cytoscape.use(fcose); registered = true; }
    const c = cytoscape({
      container: el.current!, minZoom: 0.2, maxZoom: 4,
      style: [
        { selector: "node", style: { "background-color": "data(color)", label: "data(label)", color: "#e8ecf4", "font-size": 9, "text-valign": "bottom", "text-margin-y": 3, width: "data(size)", height: "data(size)", "text-outline-width": 2, "text-outline-color": "#0b0f17" } },
        { selector: "node[kind='ghost']", style: { "background-opacity": 0.15, "border-width": 1, "border-style": "dashed", "border-color": "#8a93a6" } },
        { selector: "node:selected", style: { "border-width": 3, "border-color": "#fff" } },
        { selector: "edge", style: { width: 1.2, "line-color": "#6b7da8", "curve-style": "bezier", opacity: 0.8 } },
        { selector: "edge[explicit = 0]", style: { "line-style": "dashed", opacity: 0.4, "line-color": "#8c80b8" } },
        { selector: "edge[kind='in_project']", style: { opacity: 0.2, width: 0.8 } },
        { selector: "edge[kind='link']", style: { "target-arrow-shape": "triangle", "target-arrow-color": "#6b7da8" } },
      ] as any,
    });
    c.on("tap", "node", (e) => sel.current(e.target.id()));
    c.on("tap", (e) => { if (e.target === c) sel.current(null); });
    cy.current = c;
    return () => { c.destroy(); cy.current = null; };
  }, []);

  useEffect(() => {
    const c = cy.current; if (!c) return;
    const have = new Set(c.nodes().map((n) => n.id()));
    const want = new Set(nodes.map((n) => n.id));
    c.batch(() => {
      c.nodes().filter((n) => !want.has(n.id())).remove();
      nodes.forEach((n) => {
        const d = { id: n.id, label: n.label, kind: n.kind, color: colorOf(n), size: n.kind === "project" ? 26 : 10 + Math.min(14, Math.sqrt(n.degree + n.read_count) * 3) };
        if (have.has(n.id)) c.getElementById(n.id).data(d); else c.add({ data: d });
      });
      c.edges().remove();
      edges.forEach((e, i) => c.add({ data: { id: `e${i}`, source: e.src, target: e.dst, kind: e.kind, explicit: e.explicit ? 1 : 0 } }));
    });
    if (nodes.some((n) => !have.has(n.id))) {
      c.layout({ name: "fcose", animate: false, randomize: !have.size, fit: !have.size, nodeRepulsion: 9000, idealEdgeLength: 70 } as any).run();
    }
  }, [nodes, edges]);

  useEffect(() => {
    const c = cy.current; if (!c) return;
    c.nodes().unselect();
    if (selected) {
      const n = c.getElementById(selected);
      if (n.nonempty()) { n.select(); if (focusTick) c.animate({ center: { eles: n }, zoom: Math.max(c.zoom(), 1.2) }, { duration: 400 }); }
    }
  }, [selected, focusTick]);

  return <div ref={el} className="graph-wrap" data-testid="graph2d" />;
}
