import { useCallback, useEffect, useRef, useState } from "react";
import { getGraph, type GEdge, type GNode, type GraphData } from "./api";

export type LiveState = "live" | "reconnecting" | "paused";
export interface Status { scanning: boolean; done: number; total: number; last_update: number | null; error: string | null }

export const edgeKey = (e: { src: string; dst: string; kind: string }) => `${e.src}|${e.dst}|${e.kind}`;

export interface Delta { seq: number; type: string; data: any }

/** Pure reducer: apply a batch of deltas to maps. Returns the touched node ids (for the "firing" flare). */
export function applyDeltas(nodes: Map<string, GNode>, edges: Map<string, GEdge>, deltas: Delta[]): Set<string> {
  const touched = new Set<string>();
  for (const d of deltas) {
    if (d.type === "node_upsert") { nodes.set(d.data.id, d.data); touched.add(d.data.id); }
    else if (d.type === "node_delete") { nodes.delete(d.data.id); for (const [k, e] of edges) if (e.src === d.data.id || e.dst === d.data.id) edges.delete(k); }
    else if (d.type === "edge_upsert") { edges.set(edgeKey(d.data), d.data); touched.add(d.data.src); touched.add(d.data.dst); }
    else if (d.type === "edge_delete") edges.delete(edgeKey(d.data));
  }
  return touched;
}

/** Sequence check: returns true when `seq` directly follows `last` (otherwise the client must resync). */
export const inOrder = (last: number, seq: number) => seq === last + 1;

export function useLiveGraph() {
  const [g, setG] = useState<GraphData>({ seq: 0, nodes: [], edges: [] });
  const [state, setState] = useState<LiveState>("reconnecting");
  const [status, setStatus] = useState<Status | null>(null);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [flares, setFlares] = useState<Set<string>>(new Set());
  const [metricsTick, setMetricsTick] = useState(0);
  const [healthTick, setHealthTick] = useState(0);
  const [paused, setPaused] = useState(false);
  const nodes = useRef(new Map<string, GNode>());
  const edges = useRef(new Map<string, GEdge>());
  const last = useRef(0);
  const queue = useRef<Delta[]>([]);
  const pausedRef = useRef(false);
  const ready = useRef(false);
  const es = useRef<EventSource | null>(null);

  const publish = useCallback(() => {
    setG({ seq: last.current, nodes: [...nodes.current.values()], edges: [...edges.current.values()] });
    setUpdated(new Date());
  }, []);

  const resync = useCallback(async () => {
    const full = await getGraph();
    nodes.current = new Map(full.nodes.map((n) => [n.id, n]));
    edges.current = new Map(full.edges.map((e) => [edgeKey(e), e]));
    last.current = full.seq; queue.current = [];
    ready.current = true;
    publish();
    return full.seq;
  }, [publish]);

  const flush = useCallback(() => {
    if (pausedRef.current || !queue.current.length) return;
    const batch = queue.current.splice(0);
    const touched = applyDeltas(nodes.current, edges.current, batch);
    publish();
    if (batch.some((d) => d.type === "metrics_changed")) setMetricsTick((t) => t + 1);
    if (batch.some((d) => d.type === "health_changed")) setHealthTick((t) => t + 1);
    if (ready.current && touched.size && touched.size < 12) {
      setFlares(touched);
      setTimeout(() => setFlares((f) => (f === touched ? new Set() : f)), 2500);
    }
  }, [publish]);

  const connect = useCallback(async () => {
    es.current?.close();
    let seq = 0;
    try { seq = await resync(); } catch { setState("reconnecting"); setTimeout(connect, 2000); return; }
    const src = new EventSource(`/api/events?since=${seq}`);
    es.current = src;
    src.onopen = () => setState(pausedRef.current ? "paused" : "live");
    src.onerror = () => { setState("reconnecting"); src.close(); setTimeout(connect, Math.min(10000, 1000 + Math.random() * 2000)); };
    src.addEventListener("resync", () => { resync(); });
    for (const t of ["node_upsert", "node_delete", "edge_upsert", "edge_delete", "metrics_changed", "health_changed"]) {
      src.addEventListener(t, (m) => {
        const seqNo = Number((m as MessageEvent).lastEventId);
        const tail = queue.current.length ? queue.current[queue.current.length - 1].seq : last.current;
        if (!inOrder(tail, seqNo)) { if (seqNo > tail) resync(); return; }  // gap -> resync; old/duplicate -> ignore
        queue.current.push({ seq: seqNo, type: t, data: JSON.parse((m as MessageEvent).data) });
        last.current = seqNo;
      });
    }
  }, [resync]);

  useEffect(() => { connect(); return () => es.current?.close(); }, [connect]);
  useEffect(() => { const t = setInterval(flush, 150); return () => clearInterval(t); }, [flush]);
  useEffect(() => { // status poll: cheap, drives the scanning progress
    let live = true;
    const poll = async () => {
      try { const s = await (await fetch("/api/status")).json(); if (live) setStatus(s); } catch { /* offline */ }
    };
    poll(); const t = setInterval(poll, 2000);
    return () => { live = false; clearInterval(t); };
  }, []);

  const togglePause = useCallback(() => {
    pausedRef.current = !pausedRef.current;
    setPaused(pausedRef.current);
    setState(pausedRef.current ? "paused" : es.current?.readyState === 1 ? "live" : "reconnecting");
  }, []);

  return { g, state, status, updated, flares, metricsTick, healthTick, paused, togglePause, resync };
}
