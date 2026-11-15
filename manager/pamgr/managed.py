"""管理下（UC3）: 点検の最初に探索し、管理に入れるものを決める。

- ホーム（~/.claude・~/.gemini/config）と、.pair-agent/ を持つプロジェクト（Pair Agent を導入済み）→ 自動で管理に入れる（事後報告・取り消せる）
- .pair-agent/ を持たないリポジトリ（他人のリポジトリかもしれない）→ 判断待ち J3「管理に入れる／外す」。外したものは二度と聞かない
- マスター（このリポジトリ）は配布元なので入れない
"""

from __future__ import annotations

from typing import Any

from . import changes, inbox, settings, status, targets


def scan() -> dict[str, Any]:
    s = settings.get()
    found = targets.discover(s["scan_roots"], int(s["scan_depth"]))
    ex = {p.lower() for p in inbox.excluded()}
    register, ask = [], []
    for c in found:
        if c.get("registered") or c.get("is_master") or c["path"].lower() in ex:
            continue
        if c["kind"] != "project" or ".pair-agent" in c.get("markers", []):
            register.append(c)
        else:
            ask.append(c)
    return {"register": register, "ask": ask, "roots": s["scan_roots"]}


def j3_items(ask: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for c in ask:
        marks = "・".join(c.get("markers", []))
        out.append({
            "kind": "J3", "key": f"J3|{c['path'].lower()}", "title": f"{c['name']} を管理に入れるか",
            "what": "規則のファイルを持つリポジトリが見つかりました。.pair-agent/ が無いので、他人のリポジトリかもしれません。"
                    "管理に入れると、このプロジェクトの規則も「同時に効く規則の矛盾」の検査に入ります。",
            "applies": f"{c['path']}（{marks} あり）", "refs": {"path": c["path"], "name": c["name"], "markers": c.get("markers", [])},
            "options": [{"id": "include", "label": "管理に入れる", "primary": True}, {"id": "exclude", "label": "外す（二度と聞かない）"},
                        {"id": "later", "label": "あとで"}]})
    return out


def include(c: dict[str, Any], why: str, kind: str = "manage", what: str = "管理に入れた", refs: dict[str, Any] | None = None) -> dict[str, Any]:
    targets.register([{"kind": c["kind"], "path": c["path"], "name": c["name"]}])
    tid = targets.target_id(c["kind"], c["path"])
    return changes.record(kind, what, f"{c['name']}（{c['path']}）", why,
                          refs={"manage": "include", "target_id": tid, "path": c["path"], **(refs or {})})


def exclude(tid_or_path: str, why: str, kind: str = "manage", what: str = "管理から外した", refs: dict[str, Any] | None = None) -> dict[str, Any]:
    t = targets.get_target(tid_or_path)
    path = t["path"] if t else tid_or_path
    if t:
        targets.unregister(t["id"])
    inbox.exclude(path)
    return changes.record(kind, what, f"{t['name'] if t else path}（{path}）", why,
                          refs={"manage": "exclude", "path": path, "kind_": t["kind"] if t else "project",
                                "name": t["name"] if t else path, **(refs or {})})


def after_undo(refs: dict[str, Any]) -> None:
    """管理に入れた・外したを取り消す。"""
    if refs.get("manage") == "include" and refs.get("target_id"):
        targets.unregister(refs["target_id"])
        if not refs.get("item_id"):
            inbox.exclude(refs["path"])        # 自動で入れたものを取り消した → 二度と自動で入れない
    elif refs.get("manage") == "exclude":
        inbox.unexclude(refs["path"])
        if not refs.get("item_id"):
            targets.register([{"kind": refs.get("kind_", "project"), "path": refs["path"], "name": refs.get("name", "")}])


def overview() -> dict[str, Any]:
    rows = status.summary()
    return {"targets": rows, "excluded": inbox.excluded(),
            "pending": [i for i in inbox.items() if i["kind"] == "J3"]}
