"""判断待ち（J1〜J4）の置き場。点検が見つけるたびに鍵で重ねる（同じものを 2 回出さない）。

状態:
  open      判断待ち（通知し、数に入れる）
  info      急ぎではない（AI が「状況次第で両方真」と見た組など。通知せず、下にたたんで出す）
  later     「あとで」（下の段に出す）
  decided   判断して反映した
  dismissed 「このままでよい」「外す」（同じ鍵では二度と出さない）
  gone      点検で見つからなくなった（中身が変わった・誰かが直した）
"""

from __future__ import annotations

import hashlib
from typing import Any

from . import store

FILE = "inbox.json"
ORDER = {"J1": 0, "J2": 1, "J4": 2, "J3": 3}
ACTIVE = ("open", "info", "later")


def _load() -> dict[str, Any]:
    d = store.load(FILE, {})
    d.setdefault("items", {})
    d.setdefault("notified", [])
    return d


def item_id(key: str) -> str:
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:10]


def upsert(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """見つけたものを載せる。新しく載ったものを返す。判断済み・外したものは戻さない。"""
    d = _load()
    new = []
    for it in items:
        iid = item_id(it["key"])
        cur = d["items"].get(iid)
        if cur is None or cur["status"] == "gone":
            d["items"][iid] = {**it, "id": iid, "status": it.get("initial_status", "open"), "created_at": store.now_iso(), "seen_at": store.now_iso()}
            new.append(d["items"][iid])
        else:
            keep = {k: cur[k] for k in ("status", "created_at", "decision", "draft") if k in cur}
            d["items"][iid] = {**it, "id": iid, **keep, "seen_at": store.now_iso()}
    store.save(FILE, d)
    return new


def sync(kinds: tuple[str, ...], detected: set[str]) -> int:
    """その種類で、今回見つからなかった open・later を gone にする。"""
    d = _load()
    n = 0
    for it in d["items"].values():
        if it["kind"] in kinds and it["status"] in ACTIVE and it["key"] not in detected:
            it["status"] = "gone"
            it["gone_at"] = store.now_iso()
            n += 1
    store.save(FILE, d)
    return n


def items(statuses: tuple[str, ...] = ACTIVE) -> list[dict[str, Any]]:
    out = [it for it in _load()["items"].values() if it["status"] in statuses]
    rank = {"open": 0, "later": 1, "info": 2}
    return sorted(out, key=lambda it: (rank.get(it["status"], 3), ORDER.get(it["kind"], 9), it.get("created_at", "")))


def get(iid: str) -> dict[str, Any] | None:
    return _load()["items"].get(iid)


def update(iid: str, **fields: Any) -> dict[str, Any]:
    d = _load()
    it = d["items"].get(iid)
    if it is None:
        raise KeyError(f"判断待ちが無い: {iid}")
    it.update(fields)
    store.save(FILE, d)
    return it


def unnotified() -> list[dict[str, Any]]:
    d = _load()
    seen = set(d["notified"])
    return [it for it in items(("open",)) if it["id"] not in seen]


def mark_notified(ids: list[str]) -> None:
    d = _load()
    d["notified"] = list(dict.fromkeys(d["notified"] + ids))[-5000:]
    store.save(FILE, d)


def excluded() -> list[str]:
    return store.load(FILE, {}).get("excluded", [])


def exclude(path: str) -> None:
    d = _load()
    ex = d.setdefault("excluded", [])
    if path.lower() not in {p.lower() for p in ex}:
        ex.append(path)
    store.save(FILE, d)


def unexclude(path: str) -> None:
    d = _load()
    d["excluded"] = [p for p in d.get("excluded", []) if p.lower() != path.lower()]
    store.save(FILE, d)
