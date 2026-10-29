export interface GNode {
  id: string; kind: string; label: string; project: string | null; type: string;
  tokens_est: number; read_count: number; last_read_at: string | null; flags: string[]; degree: number;
  mtime: number; path: string | null; description?: string;
  [k: string]: any;
}
export interface GEdge { src: string; dst: string; kind: string; weight: number; explicit: boolean }
export interface GraphData { seq: number; nodes: GNode[]; edges: GEdge[] }

async function j<T>(url: string, init?: RequestInit): Promise<T> {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${url}: ${r.status}`);
  return r.json();
}
export const getGraph = () => j<GraphData>("/api/graph");
export const getNode = (id: string) => j<any>("/api/node/" + encodeURIComponent(id).replace(/%2F/g, "/"));
export const getTree = () => j<any[]>("/api/tree");
export const getHealth = () => j<any[]>("/api/health");
export const rescan = () => j<any>("/api/rescan", { method: "POST" });
