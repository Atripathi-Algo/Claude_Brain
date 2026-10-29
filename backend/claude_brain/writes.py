"""Phase 3 write-back. Every write: gated by the read-only setting, confined to allow-listed
memory folders, atomic (temp + rename), backed up into the trash first, journaled for undo,
and refused if the file changed since it was loaded (optimistic concurrency)."""
import difflib
import hashlib
import json
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

from . import config, parsers
from .redact import redact

FROZEN = "sales-insight-demo"
MAX_BYTES = 200 * 1024
_LINK = re.compile(r"\[\[([^\[\]\n|]+?)((?:\|[^\]\n]*)?)\]\]")
_FM = re.compile(r"\A﻿?---\r?\n.*?\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)


class WriteError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


def sha(b):
    return hashlib.sha256(b).hexdigest()


def slug(s):
    return re.sub(r"[^a-z0-9_-]+", "-", s.lower()).strip("-")[:80]


class Writer:
    def __init__(self, brain, svc, trash_dir=None):
        self.brain, self.svc = brain, svc
        self.trash = Path(trash_dir or (Path(brain.state_path).parent / "trash"))
        self.lock = threading.RLock()

    # ---------- guards ----------
    def enabled(self):
        return not config.load().get("read_only", True)

    def require_enabled(self):
        if not self.enabled():
            raise WriteError(403, "Read-only mode is on. Turn on write mode in Settings first.")

    def memory_dirs(self):
        pdir = (self.brain.home / "projects")
        if not pdir.is_dir():
            return []
        return [(d / "memory").resolve() for d in pdir.iterdir() if (d / "memory").is_dir()]

    def allowed(self, path):
        p = Path(path).resolve()
        if p.suffix.lower() != ".md" or p.parent not in self.memory_dirs():
            raise WriteError(403, "Path is outside the allow-listed memory folders.")
        if FROZEN in str(p).lower():
            raise WriteError(403, "This folder is frozen and never modified.")
        return p

    def node_path(self, nid):
        n = self.brain.nodes.get(nid)
        if not n or n["kind"] not in ("memory", "index") or not n["path"]:
            raise WriteError(404, "Unknown or non-editable node.")
        return self.allowed(n["path"])

    def folder_of(self, project_id):
        if not project_id.startswith("proj:"):
            raise WriteError(400, "Bad project id.")
        d = (self.brain.home / "projects" / project_id[5:] / "memory")
        return self.allowed(d / "x.md").parent

    # ---------- reading for the editor ----------
    def load(self, nid):
        p = self.node_path(nid)
        raw = p.read_bytes()
        text = raw.decode("utf-8", errors="replace")
        if redact(text) != text:
            raise WriteError(422, "This note contains secret-like text, so it is not editable here (it would be redacted). Edit it in your own editor.")
        return {"id": nid, "text": text.replace("\r\n", "\n"), "hash": sha(raw), "mtime": p.stat().st_mtime,
                "crlf": "\r\n" in text}

    # ---------- journal / backup ----------
    def _journal_path(self):
        return self.trash / "journal.json"

    def _journal(self):
        try:
            return json.loads(self._journal_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []

    def _save_journal(self, j):
        self.trash.mkdir(parents=True, exist_ok=True)
        self._journal_path().write_text(json.dumps(j[-200:], indent=1), encoding="utf-8")

    def _begin(self, op, desc):
        oid = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        d = self.trash / oid
        d.mkdir(parents=True, exist_ok=True)
        return {"id": oid, "ts": time.time(), "op": op, "desc": desc, "dir": str(d), "files": []}

    def _backup(self, entry, path):
        """Copy the current file into the trash before changing it. Returns backup path or None."""
        path = Path(path)
        if not path.exists():
            entry["files"].append({"path": str(path), "backup": None})
            return
        b = Path(entry["dir"]) / f"{len(entry['files'])}-{path.name}"
        shutil.copy2(path, b)
        entry["files"].append({"path": str(path), "backup": str(b)})

    def _write(self, path, text, crlf=False):
        data = text.replace("\r\n", "\n")
        if crlf:
            data = data.replace("\n", "\r\n")
        raw = data.encode("utf-8")
        if len(raw) > MAX_BYTES:
            raise WriteError(413, "Note is too large.")
        tmp = path.with_name(path.name + ".brain-tmp")
        with open(tmp, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)

    def _delete(self, entry, path):
        """Deleting always means: move into the trash, never permanent."""
        shutil.move(str(path), str(Path(entry["dir"]) / f"{len(entry['files'])}-deleted-{Path(path).name}"))

    def _commit(self, entry):
        for f in entry["files"]:
            p = Path(f["path"])
            f["after"] = sha(p.read_bytes()) if p.exists() else None
        j = self._journal()
        j.append(entry)
        self._save_journal(j)
        self.svc.refresh(scan_transcripts=False)
        return {"op": entry["id"], "desc": entry["desc"], "files": [Path(f["path"]).name for f in entry["files"]]}

    def _check_hash(self, path, base_hash):
        cur = sha(path.read_bytes()) if path.exists() else None
        if cur != base_hash:
            raise WriteError(409, f"{path.name} changed on disk since it was loaded. Reload and retry.")

    # ---------- operations ----------
    def preview(self, nid, content):
        info = self.load(nid)
        old, new = info["text"].splitlines(keepends=True), content.replace("\r\n", "\n").splitlines(keepends=True)
        return {"diff": "".join(difflib.unified_diff(old, new, "current", "edited", n=2)), "changed": old != new}

    def edit(self, nid, content, base_hash):
        self.require_enabled()
        with self.lock:
            p = self.node_path(nid)
            info = self.load(nid)
            self._check_hash(p, base_hash)
            if redact(content) != content:
                raise WriteError(422, "Refusing to save secret-like text.")
            e = self._begin("edit", f"Edit {p.name}")
            self._backup(e, p)
            self._write(p, content, info["crlf"])
            return self._commit(e)

    def create(self, project, name, ntype, description, body):
        self.require_enabled()
        with self.lock:
            folder = self.folder_of(project)
            fname = slug(name) + ".md"
            if fname == ".md":
                raise WriteError(400, "Name is empty.")
            p = self.allowed(folder / fname)
            if p.exists():
                raise WriteError(409, f"{fname} already exists.")
            desc = " ".join(description.split())
            text = f"---\nname: {slug(name)}\ndescription: {desc}\nmetadata:\n  type: {ntype}\n---\n{body.strip()}\n"
            e = self._begin("create", f"Create {fname}")
            self._backup(e, p)
            self._write(p, text)
            self._edit_index(e, folder, add=[(slug(name), fname, desc)])
            return self._commit(e)

    def trash_note(self, nid, base_hash):
        self.require_enabled()
        with self.lock:
            p = self.node_path(nid)
            if p.name == "MEMORY.md":
                raise WriteError(400, "MEMORY.md cannot be trashed.")
            self._check_hash(p, base_hash)
            e = self._begin("trash", f"Trash {p.name}")
            self._backup(e, p)
            self._delete(e, p)
            self._edit_index(e, p.parent, remove=[p.name])
            return self._commit(e)

    def merge(self, ids, base_hashes):
        """ids[0] is kept; the rest are merged into it, links rewritten, index lines removed, files trashed."""
        self.require_enabled()
        with self.lock:
            if len(ids) < 2 or len(set(ids)) != len(ids):
                raise WriteError(400, "Pick at least two different notes.")
            paths = [self.node_path(i) for i in ids]
            if any(p.name == "MEMORY.md" for p in paths):
                raise WriteError(400, "MEMORY.md cannot be merged.")
            for i, p in zip(ids, paths):
                self._check_hash(p, base_hashes.get(i))
            infos = [self.load(i) for i in ids]
            notes = [parsers.parse_note(p) for p in paths]
            keep_name = notes[0]["name"]
            m = _FM.match(infos[0]["text"])
            head = m.group(0) if m else ""
            body = infos[0]["text"][len(head):].rstrip()
            for n in notes[1:]:
                body += f"\n\n## Merged from {n['name']}\n\n{n['body'].strip()}"
            merged_names = {n["name"] for n in notes[1:]}
            body = self._rewrite_links(body, merged_names, keep_name)
            e = self._begin("merge", f"Merge {', '.join(sorted(merged_names))} into {keep_name}")
            self._backup(e, paths[0])
            self._write(paths[0], head + body + "\n", infos[0]["crlf"])
            for p in paths[1:]:
                self._backup(e, p)
                self._delete(e, p)
            for folder in self.memory_dirs():  # rewrite [[links]] in every other note
                for f in folder.glob("*.md"):
                    if f in paths or f.name == "MEMORY.md":
                        continue
                    raw = f.read_bytes().decode("utf-8", errors="replace")
                    new = self._rewrite_links(raw, merged_names, keep_name)
                    if new != raw:
                        self._backup(e, f)
                        self._write(f, new, "\r\n" in raw)
            for p in paths[1:]:
                self._edit_index(e, p.parent, remove=[p.name])
            return self._commit(e)

    def index_edit(self, project, action, file, title="", hook=""):
        self.require_enabled()
        with self.lock:
            folder = self.folder_of(project)
            file = Path(file).name
            e = self._begin("index", f"{action} index line for {file}")
            if action == "add":
                if not (folder / file).exists():
                    raise WriteError(404, f"{file} does not exist.")
                self._edit_index(e, folder, add=[(title or Path(file).stem, file, " ".join(hook.split()))])
            elif action == "remove":
                self._edit_index(e, folder, remove=[file])
            else:
                raise WriteError(400, "action must be add or remove")
            return self._commit(e)

    # ---------- helpers ----------
    @staticmethod
    def _rewrite_links(text, old_names, new_name):
        return _LINK.sub(lambda m: f"[[{new_name}{m.group(2)}]]" if m.group(1).strip() in old_names else m.group(0), text)

    def _edit_index(self, entry, folder, add=(), remove=()):
        """Keep MEMORY.md consistent: `- [Title](file.md) — hook`, one line per note."""
        idx = self.allowed(Path(folder) / "MEMORY.md")
        old = idx.read_bytes().decode("utf-8", errors="replace") if idx.exists() else "# Memory Index\n\n"
        crlf = "\r\n" in old
        lines = old.replace("\r\n", "\n").split("\n")
        drop = set(remove) | {f for _, f, _ in add}
        lines = [l for l in lines if not any(re.search(r"\]\(" + re.escape(f) + r"\)", l) for f in drop)]
        while lines and lines[-1] == "":
            lines.pop()
        for title, f, hook in add:
            lines.append(f"- [{title}]({f})" + (f" — {hook}" if hook else ""))
        new = "\n".join(lines) + "\n"
        if new != old.replace("\r\n", "\n"):
            if not any(x["path"] == str(idx) for x in entry["files"]):
                self._backup(entry, idx)
            self._write(idx, new, crlf)

    # ---------- undo ----------
    def history(self):
        return [{"id": j["id"], "desc": j["desc"], "ts": j["ts"]} for j in self._journal()[-10:]][::-1]

    def undo(self):
        self.require_enabled()
        with self.lock:
            j = self._journal()
            if not j:
                raise WriteError(404, "Nothing to undo.")
            e = j[-1]
            for f in e["files"]:  # refuse if anything changed since the operation
                p = Path(f["path"])
                cur = sha(p.read_bytes()) if p.exists() else None
                if cur != f.get("after"):
                    raise WriteError(409, f"{p.name} changed after this operation, so it cannot be undone safely.")
            d = Path(e["dir"])
            for f in reversed(e["files"]):
                p = Path(f["path"])
                if f["backup"]:
                    tmp = p.with_name(p.name + ".brain-tmp")
                    shutil.copy2(f["backup"], tmp)
                    os.replace(tmp, p)
                elif p.exists():  # file was created by the op: move to trash, never delete
                    shutil.move(str(p), str(d / f"undone-{p.name}"))
            self._save_journal(j[:-1])
            self.svc.refresh(scan_transcripts=False)
            return {"undone": e["desc"]}
