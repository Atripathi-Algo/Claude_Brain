"""What the app caches on disk and in memory, and a confirmed way to delete it.
Only the app's own data is ever touched: never ~/.claude, transcripts, notes or settings."""
import shutil
import threading
from pathlib import Path

from . import metrics


class CacheError(Exception):
    def __init__(self, status, detail):
        super().__init__(detail)
        self.status, self.detail = status, detail


def _tree_size(p):
    p = Path(p)
    if p.is_file():
        return p.stat().st_size, 1
    total = files = 0
    if p.is_dir():
        for f in p.rglob("*"):
            if f.is_file():
                try:
                    total += f.stat().st_size
                    files += 1
                except OSError:
                    pass
    return total, files


def items(brain, writer):
    state = Path(brain.state_path)
    state_bytes, _ = _tree_size(state)
    trash_bytes, trash_files = _tree_size(writer.trash)
    ops = len(writer._journal())
    return [
        {"id": "scan_state", "label": "Transcript scan data", "path": str(state), "bytes": state_bytes,
         "files": 1 if state.exists() else 0, "persistent": True, "warning": None,
         "description": "Read offsets, token usage per day and memory-read counts taken from your transcripts. "
                        "Deleting it makes the next scan re-read every transcript (about 20 s for ~1 GB); nothing is lost."},
        {"id": "discovery", "label": "Project discovery cache", "path": "memory only", "bytes": 0,
         "files": len(brain._disk[0]) + len(brain._cwd), "persistent": False, "warning": None,
         "description": f"{len(brain._cwd)} project folders and {len(brain._disk[0])} on-disk projects remembered for a few "
                        "minutes. Deleting it forces a fresh folder scan on the next refresh."},
        {"id": "search_index", "label": "Search index", "path": "memory only", "bytes": 0,
         "files": 1 if metrics._fts["db"] is not None else 0, "persistent": False, "warning": None,
         "description": "In-memory full-text index of your notes. It is rebuilt on the next search."},
        {"id": "trash", "label": "Undo backups (trash)", "path": str(writer.trash), "bytes": trash_bytes,
         "files": trash_files, "persistent": True,
         "warning": f"Deleting this permanently removes {ops} undo step(s) and the backups of notes you edited, merged or trashed.",
         "description": "Copies of every note changed or removed in write mode, plus the undo journal."},
    ]


def clear(brain, svc, writer, ids):
    known = {i["id"] for i in items(brain, writer)}
    bad = [i for i in ids if i not in known]
    if bad or not ids:
        raise CacheError(400, f"Unknown cache item(s): {', '.join(bad) or '(none given)'}")
    done, rescan = [], False
    with svc.refresh_lock:  # never delete state while a refresh is using it
        with brain.lock:
            if "scan_state" in ids:
                brain.state = {"v": brain.state.get("v")}
                try:
                    Path(brain.state_path).unlink()
                except FileNotFoundError:
                    pass
                done.append("scan_state")
                rescan = True
            if "discovery" in ids:
                brain._cwd.clear()
                brain._disk = ([], 0.0)
                done.append("discovery")
                rescan = True
            if "search_index" in ids:
                metrics._fts.update(key=None, db=None)
                done.append("search_index")
            if "trash" in ids:
                t = Path(writer.trash)
                if t.name != "trash" or t.parent != Path(brain.state_path).parent:  # belt and braces
                    raise CacheError(500, "Refusing to delete an unexpected folder.")
                shutil.rmtree(t, ignore_errors=True)
                done.append("trash")
    if rescan:
        threading.Thread(target=svc.refresh, daemon=True, name="brain-rescan-after-clear").start()
    return {"cleared": done, "rescanning": rescan}
