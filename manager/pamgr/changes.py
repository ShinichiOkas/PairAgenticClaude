"""書き込みの一本道: マスター・配布先へのすべての書き込みはここを通る。

- 書く前に、いまの中身が計画のときと同じか確かめる（違えば Stale。黙って潰さない）
- 書く前の版と書いた後の版を退避する（data_home/backups/<出来事の ID>/）
- 台帳（最後に配った版）を更新し、配った版の中身を「元の版」として残す（次の節のマージの基準）
- 「自動でやったこと」に 1 件の出来事として記録する。取り消しは退避した版と台帳を元に戻し、同じ動作を繰り返さない印を残す
"""

from __future__ import annotations

import difflib
import hashlib
import shutil
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import store
from .paths import data_home

ACTIVITY = "activity.json"
SUPPRESS = "suppress.json"
LEDGER = "ledger.json"
LOCK = threading.RLock()
MAX_EVENTS = 2000


class Stale(RuntimeError):
    pass


def sha(data: bytes | None) -> str | None:
    return hashlib.sha1(data).hexdigest() if data is not None else None


def ckey(data: bytes | None) -> str | None:
    """中身の鍵: 文字なら改行・空白の違いを除いた中身のハッシュ（PC ごとの改行の設定で揺れない）。文字でなければバイトのハッシュ。"""
    if data is None:
        return None
    try:
        from .survey import norm_text
        return "t" + hashlib.sha1(norm_text(data.decode("utf-8")).encode("utf-8")).hexdigest()
    except UnicodeDecodeError:
        return "b" + hashlib.sha1(data).hexdigest()


def read(p: Path) -> bytes | None:
    try:
        return p.read_bytes() if p.is_file() else None
    except OSError:
        return None


@dataclass
class Write:
    path: Path
    data: bytes | None          # None は消す
    expect: str | None          # いまの中身のハッシュ（無いはずなら None）


@dataclass
class LedgerSet:
    tid: str
    rel: str
    hash: str
    data: bytes                 # 配った版の中身（元の版として残す）


@dataclass
class Event:
    kind: str                   # distribute / adopt / merge / decide / manage / undo
    what: str
    detail: str
    why: str
    writes: list[Write] = field(default_factory=list)
    ledgers: list[LedgerSet] = field(default_factory=list)
    suppress_key: str = ""
    refs: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------- 台帳
def ledger() -> dict[str, dict[str, Any]]:
    return store.load(LEDGER, {})


def _base_path(tid: str, rel: str) -> Path:
    return data_home() / "base" / tid / rel


def base_text(tid: str, rel: str, last_hash: str | None) -> str | None:
    """最後に配った版の中身。台帳のハッシュと合うときだけ返す。"""
    if not last_hash:
        return None
    data = read(_base_path(tid, rel))
    if data is None or ckey(data) != last_hash:
        return None
    return data.decode("utf-8", errors="replace")


def set_ledger_many(items: list[LedgerSet]) -> list[dict[str, Any]]:
    """台帳を書き、書く前の値を返す（取り消し用）。"""
    led = ledger()
    before = []
    for it in items:
        before.append({"tid": it.tid, "rel": it.rel, "before": (led.get(it.tid) or {}).get(it.rel), "after": None})
        entry = {"hash": it.hash, "at": store.now_iso()}
        led.setdefault(it.tid, {})[it.rel] = entry
        before[-1]["after"] = entry
        bp = _base_path(it.tid, it.rel)
        bp.parent.mkdir(parents=True, exist_ok=True)
        bp.write_bytes(it.data)
    store.save(LEDGER, led)
    return before


def _restore_ledger(rows: list[dict[str, Any]]) -> None:
    led = ledger()
    for r in rows:
        t = led.setdefault(r["tid"], {})
        if r["before"] is None:
            t.pop(r["rel"], None)
        else:
            t[r["rel"]] = r["before"]
    store.save(LEDGER, led)


# ---------------------------------------------------------------- 繰り返さない印
def suppressed() -> dict[str, Any]:
    return store.load(SUPPRESS, {})


def suppress(key: str, why: str) -> None:
    if not key:
        return
    s = suppressed()
    s[key] = {"at": store.now_iso(), "why": why}
    store.save(SUPPRESS, s)


# ---------------------------------------------------------------- 出来事
def events() -> list[dict[str, Any]]:
    return store.load(ACTIVITY, {"events": []})["events"]


def _save_events(ev: list[dict[str, Any]]) -> None:
    store.save(ACTIVITY, {"events": ev[-MAX_EVENTS:]})


def commit(ev: Event) -> dict[str, Any]:
    """書き込みを確かめて実行し、出来事を記録して返す。どれか 1 つでも計画と違えば何も書かずに Stale。"""
    with LOCK:
        for w in ev.writes:
            now = sha(read(w.path))
            if now != w.expect:
                raise Stale(f"計画の後で変わった: {w.path}")
        eid = datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
        bdir = data_home() / "backups" / eid
        rows = []
        for n, w in enumerate(ev.writes):
            before = read(w.path)
            row: dict[str, Any] = {"path": str(w.path), "before": None, "after": None, "before_hash": sha(before), "after_hash": sha(w.data)}
            if before is not None:
                bp = bdir / f"{n}-before-{w.path.name}"
                bp.parent.mkdir(parents=True, exist_ok=True)
                bp.write_bytes(before)
                row["before"] = str(bp)
            if w.data is not None:
                ap = bdir / f"{n}-after-{w.path.name}"
                ap.parent.mkdir(parents=True, exist_ok=True)
                ap.write_bytes(w.data)
                row["after"] = str(ap)
                w.path.parent.mkdir(parents=True, exist_ok=True)
                w.path.write_bytes(w.data)
            elif w.path.exists():
                w.path.unlink()
            rows.append(row)
        led_rows = set_ledger_many(ev.ledgers) if ev.ledgers else []
        rec = {"id": eid, "at": store.now_iso(), "kind": ev.kind, "what": ev.what, "detail": ev.detail, "why": ev.why,
               "changes": rows, "ledger": led_rows, "suppress_key": ev.suppress_key, "refs": ev.refs, "undone": False}
        evs = events()
        evs.append(rec)
        _save_events(evs)
        return rec


def record(kind: str, what: str, detail: str, why: str, refs: dict[str, Any] | None = None) -> dict[str, Any]:
    """ファイルを書かない出来事（管理に入れた など）。"""
    return commit(Event(kind, what, detail, why, refs=refs or {}))


def get(eid: str) -> dict[str, Any] | None:
    return next((e for e in events() if e["id"] == eid), None)


def diff(eid: str) -> list[dict[str, Any]]:
    e = get(eid)
    if e is None:
        raise KeyError(f"出来事が無い: {eid}")
    out = []
    for c in e["changes"]:
        a = (read(Path(c["before"])) or b"").decode("utf-8", errors="replace") if c["before"] else ""
        b = (read(Path(c["after"])) or b"").decode("utf-8", errors="replace") if c["after"] else ""
        text = "".join(difflib.unified_diff(a.splitlines(keepends=True), b.splitlines(keepends=True),
                                           fromfile="前", tofile="後", n=3))
        out.append({"path": c["path"], "diff": text})
    return out


def undo(eid: str) -> dict[str, Any]:
    """取り消す: 書いたファイルを前の版に戻し、台帳も戻し、同じ動作を繰り返さない印を残す。"""
    with LOCK:
        evs = events()
        e = next((x for x in evs if x["id"] == eid), None)
        if e is None:
            raise KeyError(f"出来事が無い: {eid}")
        if e.get("undone"):
            raise ValueError("もう取り消してあります")
        if e["kind"] == "undo":
            raise ValueError("取り消しは取り消せません")
        for c in e["changes"]:
            if sha(read(Path(c["path"]))) != c["after_hash"]:
                raise ValueError(f"その後さらに変わっているので、自動では戻せません: {c['path']}")
        for c in e["changes"]:
            p = Path(c["path"])
            if c["before"]:
                p.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(c["before"], p)
            elif p.exists():
                p.unlink()
        if e.get("ledger"):
            _restore_ledger(e["ledger"])
        suppress(e.get("suppress_key", ""), f"取り消し {eid}")
        e["undone"] = True
        e["undone_at"] = store.now_iso()
        _save_events(evs)
    rec = record("undo", "取り消した", f"{e['what']}: {e['detail']}", "師匠が取り消した", refs={"undid": eid, **(e.get("refs") or {})})
    return {"undone": eid, "event": rec, "refs": e.get("refs") or {}}
