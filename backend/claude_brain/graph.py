"""Build the memory graph from a claude-home directory (read-only)."""
import itertools
import json
import re
from pathlib import Path

from . import config, parsers, transcripts
from .redact import redact


def est_tokens(n_chars):
    return max(0, n_chars // 4)  # estimate: chars/4


def _ghost(name):
    return {"id": "ghost:" + name, "kind": "ghost", "label": name, "project": None, "type": "ghost",
            "path": None, "mtime": 0, "size": 0, "tokens_est": 0,
            "last_read_at": None, "read_count": 0, "flags": ["ghost"]}


class Brain:
    def __init__(self, home=None, state_path=None):
        self.home = Path(home or config.load()["claude_home"])
        self.state_path = state_path or (config.APP_DIR / "reads.json")
        self.state = {}
        self.nodes = {}
        self.edges = []
        self.notes = {}  # node id -> parsed note
        self.indexes = {}  # project node id -> index info
        self.seq = 0

    # ---- state (app's own data folder only) ----
    def _load_state(self):
        try:
            self.state = json.loads(Path(self.state_path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.state = {}

    def _save_state(self):
        try:
            Path(self.state_path).parent.mkdir(parents=True, exist_ok=True)
            Path(self.state_path).write_text(json.dumps(self.state), encoding="utf-8")
        except OSError:
            pass

    # ---- build ----
    def rebuild(self, scan_transcripts=True):
        self._load_state()
        pdir = self.home / "projects"
        if scan_transcripts and pdir.is_dir():
            if transcripts.scan(pdir, self.state):
                self._save_state()
        reads = self.state.get("reads", {})
        self.nodes, self.edges, self.notes, self.indexes = {}, [], {}, {}
        by_name = {}

        def add(n):
            self.nodes[n["id"]] = n
            return n

        cm = self.home / "CLAUDE.md"
        if cm.is_file():
            t = parsers.read_text(cm)
            add(self._node("claude_md:user", "claude_md", "User CLAUDE.md", None, "instructions", cm, t))

        if pdir.is_dir():
            for pd in sorted(p for p in pdir.iterdir() if p.is_dir()):
                mem = pd / "memory"
                if not mem.is_dir():
                    continue
                files = [f for f in mem.glob("*.md") if f.is_file()]
                if not files:
                    continue
                pid = "proj:" + pd.name
                cwd = transcripts.project_cwd(pd)
                add({"id": pid, "kind": "project", "label": Path(cwd).name if cwd else pd.name, "project": pid,
                     "type": "project", "path": cwd or str(pd), "mtime": 0, "size": 0, "tokens_est": 0,
                     "last_read_at": None, "read_count": 0, "flags": []})
                listed = {}
                iid = f"idx:{pd.name}"
                for f in sorted(files):
                    t = parsers.read_text(f)
                    if f.name == "MEMORY.md":
                        entries, nlines, size, trunc = parsers.parse_index(t)
                        n = add(self._node(iid, "index", "MEMORY.md", pid, "index", f, t))
                        if trunc:
                            n["flags"].append("index_over_cap")
                        self.indexes[pid] = {"entries": entries, "lines": nlines, "bytes": size, "truncated": trunc}
                        self.edges.append(self._edge(iid, pid, "in_project", True))
                        listed = {e["file"]: e for e in entries}
                        continue
                    note = parsers.parse_note(f)
                    nid = f"mem:{pd.name}/{f.name}"
                    n = add(self._node(nid, "memory", note["name"], pid, note["type"], f, note["text"]))
                    n["description"] = note["description"]
                    n["flags"] += [w.replace(" ", "_") for w in note["warnings"]]
                    if len(note["text"]) > 8000:
                        n["flags"].append("oversized")
                    r = reads.get(transcripts._norm(f))
                    if r:
                        n["read_count"], n["last_read_at"] = r["count"], r["last"] or None
                    self.notes[nid] = note
                    self.edges.append(self._edge(nid, pid, "in_project", True))
                    by_name.setdefault((pid, note["name"]), nid)
                    by_name.setdefault((None, note["name"]), nid)
                names = {f.name for f in files} - {"MEMORY.md"}
                if iid in self.nodes:
                    for fname in listed:
                        nid = f"mem:{pd.name}/{fname}"
                        if nid in self.nodes:
                            self.edges.append(self._edge(iid, nid, "index_of", True))
                        else:
                            self.nodes[iid]["flags"].append("dead_entry:" + fname)
                    orphans = names - set(listed)
                else:
                    orphans = names
                for fname in orphans:
                    self.nodes[f"mem:{pd.name}/{fname}"]["flags"].append("orphan")

        for nid, note in self.notes.items():
            pid = self.nodes[nid]["project"]
            for target in note["links"]:
                tid = by_name.get((pid, target)) or by_name.get((None, target))
                if not tid:
                    tid = "ghost:" + target
                    if tid not in self.nodes:
                        add(_ghost(target))
                self.edges.append(self._edge(nid, tid, "link", True))

        path2id = {transcripts._norm(n["path"]): i for i, n in self.nodes.items() if n["kind"] == "memory"}
        co = {}
        for paths in self.state.get("sessions", {}).values():
            ids = sorted({path2id[p] for p in paths if p in path2id})
            if 1 < len(ids) <= 12:
                for a, b in itertools.combinations(ids, 2):
                    co[(a, b)] = co.get((a, b), 0) + 1
        for (a, b), w in co.items():
            self.edges.append(self._edge(a, b, "co_read", False, w))

        self._similar(config.load().get("similarity_threshold", 0.6))

        seen, out = set(), []
        for e in self.edges:
            k = (e["src"], e["dst"], e["kind"])
            if k not in seen:
                seen.add(k)
                out.append(e)
        self.edges = out
        deg = {}
        for e in self.edges:
            if e["kind"] != "in_project":
                deg[e["src"]] = deg.get(e["src"], 0) + 1
                deg[e["dst"]] = deg.get(e["dst"], 0) + 1
        for i, n in self.nodes.items():
            n["degree"] = deg.get(i, 0)
        for pid, n in self.nodes.items():
            if n["kind"] == "project":
                n["tokens_est"] = sum(m["tokens_est"] for m in self.nodes.values()
                                      if m["project"] == pid and m["kind"] in ("memory", "index"))
        self.seq += 1

    def _similar(self, threshold, topk=3):
        ids = list(self.notes)
        if len(ids) < 2:
            return
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer
            from sklearn.metrics.pairwise import cosine_similarity
            docs = [self.notes[i]["body"] + " " + self.notes[i]["description"] for i in ids]
            sim = cosine_similarity(TfidfVectorizer(stop_words="english").fit_transform(docs))
        except Exception:
            return
        for a in range(len(ids)):
            cands = sorted(((sim[a][b], b) for b in range(len(ids)) if b != a), reverse=True)[:topk]
            for s, b in cands:
                if s >= threshold and a < b:
                    self.edges.append(self._edge(ids[a], ids[b], "similar", False, round(float(s), 3)))
                    if s >= 0.8:
                        for i in (ids[a], ids[b]):
                            if "duplicate_candidate" not in self.nodes[i]["flags"]:
                                self.nodes[i]["flags"].append("duplicate_candidate")

    @staticmethod
    def _edge(src, dst, kind, explicit, weight=1):
        return {"src": src, "dst": dst, "kind": kind, "explicit": explicit, "weight": weight}

    @staticmethod
    def _node(nid, kind, label, project, ntype, path, text):
        try:
            st = Path(path).stat()
            mtime, size = st.st_mtime, st.st_size
        except OSError:
            mtime = size = 0
        return {"id": nid, "kind": kind, "label": label, "project": project, "type": ntype,
                "path": str(path), "mtime": mtime, "size": size, "tokens_est": est_tokens(len(text)),
                "last_read_at": None, "read_count": 0, "flags": []}

    # ---- views ----
    def graph(self, project=None, kind=None, ntype=None, q=None):
        nodes = list(self.nodes.values())
        if project:
            nodes = [n for n in nodes if n["project"] == project or n["id"] == project]
        if kind:
            ks = set(kind.split(","))
            nodes = [n for n in nodes if n["kind"] in ks]
        if ntype:
            ts = set(ntype.split(","))
            nodes = [n for n in nodes if n["type"] in ts]
        if q:
            nodes = [n for n in nodes if q.lower() in n["label"].lower()]
        ids = {n["id"] for n in nodes}
        edges = [e for e in self.edges if e["src"] in ids and e["dst"] in ids]
        return {"seq": self.seq, "nodes": nodes, "edges": edges}

    def node_detail(self, nid):
        n = self.nodes.get(nid)
        if not n:
            return None
        d = dict(n)
        note = self.notes.get(nid)
        if note:
            d["body"] = redact(note["body"])
            d["description"] = redact(note["description"])
            d["warnings"] = note["warnings"]
        elif n["kind"] in ("index", "claude_md"):
            d["body"] = redact(parsers.read_text(n["path"]))[:20000]
        d["backlinks"] = [e["src"] for e in self.edges if e["dst"] == nid and e["kind"] == "link"]
        d["outlinks"] = [e["dst"] for e in self.edges if e["src"] == nid and e["kind"] == "link"]
        d["related"] = [{"id": (e["dst"] if e["src"] == nid else e["src"]), "kind": e["kind"], "weight": e["weight"]}
                        for e in self.edges if nid in (e["src"], e["dst"]) and e["kind"] in ("similar", "co_read")]
        return d

    def tree(self):
        out = []
        for pid, p in self.nodes.items():
            if p["kind"] != "project":
                continue
            groups = {}
            for n in self.nodes.values():
                if n["project"] == pid and n["kind"] in ("memory", "index"):
                    groups.setdefault(n["type"], []).append(
                        {"id": n["id"], "label": n["label"], "tokens_est": n["tokens_est"], "flags": n["flags"]})
            out.append({"id": pid, "label": p["label"], "tokens_est": p["tokens_est"],
                        "types": [{"type": t, "tokens_est": sum(x["tokens_est"] for x in v), "notes": v}
                                  for t, v in sorted(groups.items())]})
        return out

    def health(self):
        issues = []
        keep = ("orphan", "dead_entry", "ghost", "oversized", "index_over_cap", "duplicate_candidate",
                "malformed_frontmatter", "no_frontmatter")
        for n in self.nodes.values():
            for f in n["flags"]:
                if f.split(":")[0] in keep:
                    issues.append({"node": n["id"], "label": n["label"], "issue": f})
        for nid, note in self.notes.items():
            for ref in note["path_refs"]:
                p = ref.rsplit(":", 1)[0] if re.search(r":\d+$", ref) else ref
                if re.match(r"^[A-Za-z]:[\\/]", p) and not Path(p).exists():
                    issues.append({"node": nid, "label": self.nodes[nid]["label"], "issue": "stale_ref:" + p})
        return issues
