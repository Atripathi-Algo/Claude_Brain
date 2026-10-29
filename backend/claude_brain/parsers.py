"""Parsers for memory notes and MEMORY.md indexes. Tolerant of malformed input."""
import re
from pathlib import Path

import yaml

_FM = re.compile(r"\A﻿?---\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_LINK = re.compile(r"\[\[([^\[\]\n|]+?)(?:\|[^\]\n]*)?\]\]")
_INDEX = re.compile(r"^\s*[-*]\s*\[([^\]]*)\]\(([^)]+)\)\s*(?:[—–-]+\s*(.*))?$")
_PATHREF = re.compile(r"`([^`\n]{3,200})`")


def read_text(path):
    """Shared-read, never locks; returns '' on error."""
    try:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8", errors="replace").replace("\r\n", "\n")
    except OSError:
        return ""


def parse_note(path):
    text = read_text(path)
    warnings = []
    fm = {}
    body = text
    m = _FM.match(text)
    if m:
        body = text[m.end():]
        try:
            loaded = yaml.safe_load(m.group(1))
            if isinstance(loaded, dict):
                fm = loaded
            else:
                warnings.append("frontmatter is not a mapping")
        except yaml.YAMLError:
            warnings.append("malformed frontmatter")
            for line in m.group(1).splitlines():
                k, _, v = line.partition(":")
                if v.strip() and not line.startswith(" "):
                    fm[k.strip()] = v.strip()
    else:
        warnings.append("no frontmatter")
    meta = fm.get("metadata") if isinstance(fm.get("metadata"), dict) else {}
    ntype = fm.get("type") or meta.get("type") or "unknown"
    name = str(fm.get("name") or Path(path).stem)
    links = []
    for l in _LINK.findall(body):
        l = l.strip()
        if l and l not in links:
            links.append(l)
    return {
        "name": name,
        "description": str(fm.get("description") or ""),
        "type": str(ntype),
        "node_type": str(fm.get("node_type") or meta.get("node_type") or ""),
        "modified": str(fm.get("modified") or meta.get("modified") or ""),
        "body": body,
        "text": text,
        "links": links,
        "path_refs": [p for p in _PATHREF.findall(body) if _looks_like_path(p)],
        "warnings": warnings,
    }


def _looks_like_path(s):
    s = s.split(":")[0] if re.search(r":\d+$", s) else s
    return bool(re.search(r"[\/]", s) and re.search(r"\.\w{1,6}$", s) and " " not in s)


def parse_index(text):
    """-> (entries[{title,file,hook}], total_lines, bytes, truncated)"""
    entries = []
    lines = text.split("\n")
    for ln in lines:
        m = _INDEX.match(ln)
        if m:
            entries.append({"title": m.group(1), "file": m.group(2).strip(), "hook": (m.group(3) or "").strip()})
    size = len(text.encode("utf-8"))
    return entries, len(lines), size, (len(lines) > 200 or size > 25 * 1024)
