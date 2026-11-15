"""配布先の探索と登録。

配布先の種類:
  claude_home  ~/.claude                （全体・ユーザー固有の配布先）
  gemini_home  ~/.gemini/config         （同上・Antigravity）
  project      CLAUDE.md・.claude・.pair-agent などを持つプロジェクト
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from . import store
from .paths import master_root, user_home

FILE = "registry.json"
PROJECT_MARKERS = ("CLAUDE.md", "GEMINI.md", "AGENTS.md", ".claude", ".pair-agent", ".agents")
HOME_MARKERS = ("CLAUDE.md", "GEMINI.md", "rules", "skills", "agents", "pair-agent")
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", "site-packages", "dist", "build"}


def norm(p: str | Path) -> str:
    return str(Path(p).expanduser().resolve())


def target_id(kind: str, path: str) -> str:
    return f"{kind[0]}-" + hashlib.sha1(norm(path).lower().encode("utf-8")).hexdigest()[:10]


def global_homes() -> list[dict[str, Any]]:
    out = []
    for kind, p, name in (
        ("claude_home", user_home() / ".claude", "~/.claude"),
        ("gemini_home", user_home() / ".gemini" / "config", "~/.gemini/config"),
    ):
        if p.is_dir():
            out.append({"kind": kind, "path": norm(p), "name": name, "markers": [m for m in HOME_MARKERS if (p / m).exists()]})
    return out


def _project_markers(d: Path) -> list[str]:
    return [m for m in PROJECT_MARKERS if (d / m).exists()]


def discover(roots: list[str], depth: int) -> list[dict[str, Any]]:
    """探索: グローバルのホームと、根の下のプロジェクト。プロジェクトの中には潜らない。"""
    found: dict[str, dict[str, Any]] = {}
    for g in global_homes():
        found[g["path"].lower()] = g
    master = norm(master_root()).lower()

    def walk(d: Path, level: int) -> None:
        if level > depth:
            return
        try:
            children = sorted(c for c in d.iterdir() if c.is_dir())
        except OSError:
            return
        for c in children:
            if c.name.startswith(".") or c.name in SKIP_DIRS:
                continue
            marks = _project_markers(c)
            if marks:
                key = norm(c).lower()
                found.setdefault(key, {"kind": "project", "path": norm(c), "name": c.name, "markers": marks, "is_master": key == master})
            else:
                walk(c, level + 1)

    for r in roots:
        rp = Path(r).expanduser()
        if rp.is_dir():
            walk(rp, 1)
    regs = {t["path"].lower() for t in list_targets()}
    out = list(found.values())
    for c in out:
        c["registered"] = c["path"].lower() in regs
    order = {"claude_home": 0, "gemini_home": 1, "project": 2}
    return sorted(out, key=lambda c: (order.get(c["kind"], 9), c["name"].lower()))


def list_targets() -> list[dict[str, Any]]:
    return store.load(FILE, {"targets": []})["targets"]


def get_target(tid: str) -> dict[str, Any] | None:
    return next((t for t in list_targets() if t["id"] == tid), None)


def register(items: list[dict[str, Any]]) -> tuple[int, list[dict[str, Any]]]:
    reg = store.load(FILE, {"targets": []})
    have = {t["id"] for t in reg["targets"]}
    added = 0
    for it in items:
        kind = it.get("kind", "project")
        if kind not in ("claude_home", "gemini_home", "project"):
            raise ValueError(f"配布先の種類が不明: {kind}")
        path = norm(it["path"])
        if not Path(path).is_dir():
            raise ValueError(f"フォルダが無い: {path}")
        tid = target_id(kind, path)
        if tid in have:
            continue
        reg["targets"].append({"id": tid, "kind": kind, "path": path, "name": it.get("name") or Path(path).name, "registered_at": store.now_iso()})
        have.add(tid)
        added += 1
    store.save(FILE, reg)
    return added, reg["targets"]


def unregister(tid: str) -> bool:
    reg = store.load(FILE, {"targets": []})
    before = len(reg["targets"])
    reg["targets"] = [t for t in reg["targets"] if t["id"] != tid]
    store.save(FILE, reg)
    return len(reg["targets"]) < before
