import { useEffect, useRef, useState } from "react";
import * as echarts from "echarts";

interface Row { day: string; project: string; input: number; cache_write: number; cache_read: number; output: number }

const j = (u: string) => fetch(u).then((r) => r.json());
const css = (v: string) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();

function Chart({ title, option, csv, note }: { title: string; option: any; csv?: () => string; note?: string }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);
  useEffect(() => {
    const c = echarts.init(el.current!);
    chart.current = c;
    const ro = new ResizeObserver(() => c.resize());
    ro.observe(el.current!);
    return () => { ro.disconnect(); c.dispose(); };
  }, []);
  useEffect(() => {
    chart.current?.setOption({ backgroundColor: "transparent", textStyle: { color: css("--text") },
      grid: { left: 56, right: 24, top: 36, bottom: 56 }, tooltip: { trigger: "axis" }, legend: { top: 0, show: (option.series?.length ?? 0) <= 8, textStyle: { color: css("--muted") } }, ...option }, true);
  }, [option]);
  const download = (href: string, name: string) => { const a = document.createElement("a"); a.href = href; a.download = name; a.click(); };
  return (
    <section className="card">
      <div className="card-h"><h3>{title}</h3>
        <span>
          <button onClick={() => download(chart.current!.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: css("--panel") }), title + ".png")}>PNG</button>
          {csv && <button onClick={() => download(URL.createObjectURL(new Blob([csv()], { type: "text/csv" })), title + ".csv")}>CSV</button>}
        </span></div>
      {note && <p className="muted small">{note}</p>}
      <div ref={el} className="chart" />
    </section>
  );
}

const axis = { axisLabel: { color: "#8b95ab" }, axisLine: { lineStyle: { color: "#3a4560" } }, splitLine: { lineStyle: { color: "rgba(120,130,160,.15)" } } };
const zoom = [{ type: "inside" }, { type: "slider", height: 18, bottom: 8 }];

export default function Charts({ tick, onSelect }: { tick: number; onSelect: (id: string) => void }) {
  const [rows, setRows] = useState<Row[]>([]);
  const [extra, setExtra] = useState<any>(null);
  const [tree, setTree] = useState<any[]>([]);
  useEffect(() => {
    j("/api/metrics/tokens").then(setRows).catch(() => {});
    j("/api/metrics/extra").then(setExtra).catch(() => {});
    j("/api/tree").then(setTree).catch(() => {});
  }, [tick]);

  const days = [...new Set(rows.map((r) => r.day))].sort();
  const projects = [...new Set(rows.map((r) => r.project))];
  const sum = (day: string, p: string, k: keyof Row) => rows.filter((r) => r.day === day && r.project === p).reduce((s, r) => s + (r[k] as number), 0);
  const perDay = {
    xAxis: { type: "category", data: days, ...axis }, yAxis: { type: "value", name: "tokens", ...axis }, dataZoom: zoom,
    series: projects.map((p) => ({ name: p, type: "bar", stack: "t", data: days.map((d) => sum(d, p, "input") + sum(d, p, "cache_write") + sum(d, p, "output")) })),
  };
  const share = {
    xAxis: { type: "category", data: days, ...axis }, yAxis: { type: "value", max: 100, name: "% of input", ...axis }, dataZoom: zoom, tooltip: { trigger: "axis" },
    series: [{ name: "cache-read share", type: "line", smooth: true, areaStyle: { opacity: 0.2 }, data: days.map((d) => {
      const cr = rows.filter((r) => r.day === d).reduce((s, r) => s + r.cache_read, 0);
      const all = rows.filter((r) => r.day === d).reduce((s, r) => s + r.input + r.cache_write + r.cache_read, 0);
      return all ? +((cr / all) * 100).toFixed(1) : 0;
    }) }],
  };
  const growth = extra?.growth ?? [];
  const growthOpt = { xAxis: { type: "category", data: growth.map((g: any) => g.day), ...axis }, yAxis: { type: "value", minInterval: 1, name: "notes", ...axis },
    series: [{ name: "notes (by last-modified date)", type: "line", step: "end", data: growth.map((g: any) => g.notes) }] };
  const top = extra?.top_read ?? [];
  const topOpt = { tooltip: { trigger: "item" }, grid: { left: 190, right: 24, top: 16, bottom: 24 }, legend: { show: false },
    xAxis: { type: "value", minInterval: 1, ...axis }, yAxis: { type: "category", inverse: true, data: top.map((t: any) => t.label), ...axis },
    series: [{ type: "bar", data: top.map((t: any) => t.reads) }] };
  const tbp = extra?.types_by_project ?? {};
  const typeNames = [...new Set(Object.values(tbp).flatMap((v: any) => Object.keys(v)))] as string[];
  const typesOpt = { xAxis: { type: "category", data: Object.keys(tbp), ...axis }, yAxis: { type: "value", minInterval: 1, ...axis },
    series: typeNames.map((t) => ({ name: t, type: "bar", stack: "n", data: Object.keys(tbp).map((p) => tbp[p][t] ?? 0) })) };
  const treemap = { tooltip: { trigger: "item", formatter: (p: any) => `${p.name}<br/>~${p.value} tokens (estimate)` }, legend: { show: false }, grid: undefined,
    series: [{ type: "treemap", roam: false, nodeClick: "link", breadcrumb: { show: true }, label: { color: "#fff" },
      data: tree.map((p) => ({ name: p.label, value: p.tokens_est, children: p.types.flatMap((t: any) => t.notes.map((n: any) => ({ name: n.label, value: Math.max(1, n.tokens_est), id: n.id }))) })) }] };
  const csv = () => "day,project,input,cache_write,cache_read,output\n" + rows.map((r) => [r.day, `"${r.project}"`, r.input, r.cache_write, r.cache_read, r.output].join(",")).join("\n");

  return (
    <div className="cards">
      <Chart title="Tokens per day by project" option={perDay} csv={csv}
        note="Input + cache-write + output, from transcript usage records. Cache reads are excluded here because they dwarf everything else (see next chart)." />
      <Chart title="Cache-read share over time" option={share} />
      <Chart title="Always-loaded memory (treemap)" option={treemap} note="Estimated tokens (chars/4) per project and note." />
      <Chart title="Memory growth" option={growthOpt} note="Uses file modification dates; creation dates are unknown." />
      <Chart title="Top-read notes" option={topOpt} note="Counted from Read tool calls in transcripts." />
      <Chart title="Notes by type per project" option={typesOpt} />
      {!rows.length && <p className="muted">No token usage found yet, or the first transcript scan is still running.</p>}
    </div>
  );
}
