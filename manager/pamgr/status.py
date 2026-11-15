"""配布状況: マスターと配布先のファイルを照合する。台帳（最後に配った版）で向きを判定する。

状態:
  same          一致
  missing       未配布（配布先に無い）
  master-ahead  配布先は最後に配った版のまま。マスターが新しい
  target-ahead  マスターは最後に配った版のまま。配布先で改変された
  diverged      双方で変更
  differs       差分あり。台帳が無いので向きは不明（更新時刻のヒントを newer に付ける）
  extra         配布先にだけある（マスターに無い）
"""

from __future__ import annotations

import difflib
import hashlib
from pathlib import Path
from typing import Any

from . import mapping, store, targets
from .paths import master_root

LEDGER = "ledger.json"
STATES = ("same", "missing", "master-ahead", "target-ahead", "diverged", "differs", "extra")


def file_hash(p: Path) -> str | None:
    """中身の鍵（改行・空白の違いは同じとみなす。台帳と同じ鍵）。"""
    from .changes import ckey
    try:
        return ckey(p.read_bytes())
    except OSError:
        return None


def ledger() -> dict[str, dict[str, Any]]:
    return store.load(LEDGER, {})


def record_ledger(tid: str, rel: str, h: str) -> None:
    led = ledger()
    led.setdefault(tid, {})[rel] = {"hash": h, "at": store.now_iso()}
    store.save(LEDGER, led)


def _state(mh: str | None, th: str | None, last: str | None) -> str:
    if th is None:
        return "missing"
    if mh == th:
        return "same"
    if last is None:
        return "differs"
    if th == last:
        return "master-ahead"
    if mh == last:
        return "target-ahead"
    return "diverged"


def target_files(t: dict[str, Any], scope: str | None = None) -> list[dict[str, Any]]:
    root = Path(t["path"])
    led = ledger().get(t["id"], {})
    master = master_root()
    rows: list[dict[str, Any]] = []
    for e in mapping.entries_for(t["kind"], scope):
        if e.requires_dest_dir and not (root / e.dest).is_dir():
            continue
        known: set[str] = set()
        for src, rel in mapping.expand(e, master):
            known.add(rel)
            dest = root / rel
            mh, th = file_hash(src), file_hash(dest) if dest.is_file() else None
            st = _state(mh, th, (led.get(rel) or {}).get("hash"))
            row = {"entry": e.id, "label": e.label, "scope": e.scope, "src_rel": src.relative_to(master).as_posix(),
                   "dest_rel": rel, "state": st}
            if st == "differs":
                row["newer"] = "target" if dest.stat().st_mtime > src.stat().st_mtime else "master"
            rows.append(row)
        for rel in mapping.extra_in_target(e, root, known):
            rows.append({"entry": e.id, "label": e.label, "scope": e.scope, "src_rel": "", "dest_rel": rel, "state": "extra"})
    return rows


def summary() -> list[dict[str, Any]]:
    out = []
    for t in targets.list_targets():
        counts = {s: 0 for s in STATES}
        for r in target_files(t):
            counts[r["state"]] += 1
        out.append({**t, "counts": counts})
    return out


def _resolve(t: dict[str, Any], rel: str) -> tuple[Path | None, Path]:
    """配布先の相対パスから (マスターのファイル, 配布先のファイル) を引く。"""
    root = Path(t["path"])
    for e in mapping.entries_for(t["kind"]):
        for src, r in mapping.expand(e):
            if r == rel:
                return src, root / rel
    return None, root / rel


def _read(p: Path | None) -> list[str]:
    if p is None or not p.is_file():
        return []
    return p.read_text(encoding="utf-8", errors="replace").splitlines(keepends=True)


def diff(tid: str, rel: str) -> dict[str, Any]:
    t = targets.get_target(tid)
    if t is None:
        raise KeyError(f"配布先が無い: {tid}")
    src, dest = _resolve(t, rel)
    a, b = _read(src), _read(dest)
    text = "".join(difflib.unified_diff(a, b, fromfile=f"master/{src.relative_to(master_root()).as_posix() if src else '(なし)'}",
                                       tofile=f"{t['name']}/{rel}", n=3))
    return {"diff": text, "src": str(src) if src else None, "dest": str(dest)}


def adopt(tid: str, rel: str) -> dict[str, Any]:
    """配布先の版をマスターに取り込む（配布先で改変されたものを正とするとき）。マスターは git 管理なので戻せる。"""
    t = targets.get_target(tid)
    if t is None:
        raise KeyError(f"配布先が無い: {tid}")
    src, dest = _resolve(t, rel)
    if src is None:
        raise ValueError(f"マスターに対応するファイルが無い: {rel}")
    if not dest.is_file():
        raise ValueError(f"配布先にファイルが無い: {dest}")
    data = dest.read_bytes()
    src.write_bytes(data)
    record_ledger(tid, rel, file_hash(src) or "")
    return {"written": str(src)}
