"""判断待ちの判断を反映する（UC1）。書き込みは changes を通す（退避・台帳・自動でやったことへの記録・取り消し）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from . import changes, inbox, sweep, targets
from .changes import Event, LedgerSet, Write, read, sha
from .paths import master_root


class NotYet(NotImplementedError):
    pass


def decide(iid: str, option: str, edits: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    it = inbox.get(iid)
    if it is None:
        raise KeyError(f"判断待ちが無い: {iid}")
    if it["status"] not in inbox.ACTIVE:
        raise ValueError("この項目はもう判断済みです")
    if option == "later":
        inbox.update(iid, status="later")
        return {"status": "later"}
    handler = {"J2": _j2}.get(it["kind"])
    if handler is None:
        raise NotYet(f"inbox.decide.{it['kind']}")
    rec = handler(it, option, edits or [])
    status = "dismissed" if rec is None else "decided"
    inbox.update(iid, status=status, decision={"option": option, "event": rec["id"] if rec else None})
    return {"status": status, "event": rec}


def _j2(it: dict[str, Any], option: str, _edits: list[dict[str, Any]]) -> dict[str, Any]:
    r = it["refs"]
    t = targets.get_target(r["target_id"])
    if t is None:
        raise KeyError("配布先が管理下にありません")
    master = master_root()
    src, dest = master / r["src_rel"], Path(t["path"]) / r["rel"]
    mb, tb = read(src), read(dest)
    if sha(mb) != r["mh"] or sha(tb) != r["th"]:
        raise ValueError("判断待ちに上げた後で、ファイルが変わりました。点検し直してください")
    where = f"{t['name']}/{r['rel']}"
    refs = {"item_id": it["id"], "target_id": t["id"], "rel": r["rel"], "src_rel": r["src_rel"]}
    if option == "master":
        ev = Event("decide", "判断: マスターの版にした", f"マスターの {r['src_rel']} → {where}", "師匠の判断（J2）",
                   [Write(dest, mb, r["th"])], [LedgerSet(t["id"], r["rel"], r["mh"], mb)], refs=refs)  # type: ignore[arg-type]
    elif option == "target":
        ws = [Write(src, tb, r["mh"])] + sweep._mirror_writes(r["src_rel"], mb, tb, sweep.Overlay(), master)  # type: ignore[arg-type]
        ev = Event("decide", "判断: 配布先の版をマスターへ", f"{where} → マスターの {r['src_rel']}", "師匠の判断（J2）",
                   ws, [LedgerSet(t["id"], r["rel"], r["th"], tb)], refs=refs)  # type: ignore[arg-type]
    else:
        raise ValueError(f"選択肢が不明: {option}")
    return changes.commit(ev)


def after_undo(refs: dict[str, Any]) -> None:
    """判断を取り消したら、その判断待ちを開き直す。"""
    iid = refs.get("item_id")
    if iid and inbox.get(iid):
        inbox.update(iid, status="open", decision=None)
