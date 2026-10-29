import { expect, test } from "vitest";
import { mergeNodes, neighbours, applyFilters, defaultFilters } from "./model";

const n = (id: string, extra = {}) => ({ id, kind: "memory", label: id, project: "p", type: "user", tokens_est: 0, read_count: 0, last_read_at: null, flags: [], degree: 0, mtime: 0, path: null, ...extra });

test("mergeNodes keeps positions of existing nodes", () => {
  const m = new Map<string, any>();
  const [a] = mergeNodes(m, [n("a")]);
  a.x = 5; a.fx = 5;
  const out = mergeNodes(m, [n("a", { label: "A2" }), n("b")]);
  expect(out[0]).toBe(a); expect(out[0].x).toBe(5); expect(out[0].label).toBe("A2"); expect(out).toHaveLength(2);
  expect(mergeNodes(m, [n("b")])).toHaveLength(1);
});

test("neighbours and filters", () => {
  const e = [{ src: "a", dst: "b", kind: "link", weight: 1, explicit: true }, { src: "b", dst: "c", kind: "similar", weight: 1, explicit: false }];
  expect([...neighbours("b", e)].sort()).toEqual(["a", "b", "c"]);
  const f = defaultFilters(); f.inferred = false;
  const r = applyFilters({ seq: 1, nodes: [n("a"), n("b"), n("c")] as any, edges: e }, f);
  expect(r.edges).toHaveLength(1);
});
