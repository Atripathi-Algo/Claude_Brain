import type { GEdge, GNode, GraphData } from "./api";

export const TYPE_COLOR: Record<string, string> = {
  user: "#f5c451", feedback: "#ff7a90", project: "#5ec8ff", reference: "#7be0a0",
  index: "#b79cff", ghost: "#8a93a6", project_hub: "#ffffff", instructions: "#ffa86b", unknown: "#9aa4b8",
};
export const colorOf = (n: GNode) => (n.kind === "project" ? TYPE_COLOR.project_hub : TYPE_COLOR[n.kind === "memory" ? n.type : n.kind] ?? TYPE_COLOR[n.type] ?? TYPE_COLOR.unknown);

export interface Filters { project: string; kinds: Set<string>; types: Set<string>; inferred: boolean; q: string; recentDays: number; drive: string; emptyProjects: boolean }
export const defaultFilters = (): Filters => ({ project: "", kinds: new Set(), types: new Set(), inferred: true, q: "", recentDays: 0, drive: "", emptyProjects: true });

export function applyFilters(g: GraphData, f: Filters): { nodes: GNode[]; edges: GEdge[] } {
  const cutoff = f.recentDays ? Date.now() - f.recentDays * 864e5 : 0;
  const keep = (n: GNode) =>
    (!f.project || n.project === f.project || n.id === f.project) &&
    (!f.kinds.size || f.kinds.has(n.kind)) &&
    (!f.types.size || f.types.has(n.type)) &&
    (!f.drive || n.drive === f.drive) &&
    (f.emptyProjects || !(n.kind === "project" && n.flags.includes("no_memory"))) &&
    (!cutoff || n.mtime * 1000 >= cutoff);
  const nodes = g.nodes.filter(keep);
  const ids = new Set(nodes.map((n) => n.id));
  const edges = g.edges.filter((e) => ids.has(e.src) && ids.has(e.dst) && (f.inferred || e.explicit));
  return { nodes, edges };
}

/** Merge a new snapshot into persistent node objects so positions survive updates. */
export function mergeNodes(prev: Map<string, any>, nodes: GNode[]): any[] {
  const next = new Map<string, any>();
  for (const n of nodes) {
    const old = prev.get(n.id);
    next.set(n.id, old ? Object.assign(old, n) : { ...n });
  }
  prev.clear();
  next.forEach((v, k) => prev.set(k, v));
  return [...next.values()];
}

export function neighbours(id: string | null, edges: GEdge[]): Set<string> {
  const s = new Set<string>();
  if (!id) return s;
  s.add(id);
  for (const e of edges) { if (e.src === id) s.add(e.dst); if (e.dst === id) s.add(e.src); }
  return s;
}

export const webglOk = (): boolean => {
  try { const c = document.createElement("canvas"); return !!(c.getContext("webgl2") || c.getContext("webgl")); } catch { return false; }
};
