"""点検の GitHub の段（UC4）: マスターを pull し、ほかのユーザーの変更は J4 で確かめ、ツールが書いた変更だけを commit・push する。

- pull: fast-forward だけ。ほかのユーザー（作者のメールが自分と違う）のコミットが規則・スキルを変えていれば J4 にし、
  決めるまでその規則はこの PC へ配らない
- publish: マスターの作業ツリーの変更のうち、ツールが書いた中身（自動でやったこと・判断の反映・取り消し）のままのファイルだけ。
  師匠や別のエージェントが編集中のファイル（中身が違う）は出さない
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from . import changes, fleet, inbox
from .changes import Event, Write, read, sha
from .paths import master_root


def pull_step() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    r = fleet.pull()
    info = {k: r.get(k) for k in ("ok", "old_head", "new_head", "error", "diverged")}
    info["changed"] = len(r.get("changed") or [])
    items = []
    foreign = [c for c in (r.get("foreign") or []) if c.get("files")]
    if r.get("ok") and foreign:
        files = sorted({f for c in foreign for f in c["files"]})
        lines = "、".join(f"{c['author']}「{c['subject']}」" for c in foreign[:5])
        items.append({
            "kind": "J4", "key": f"J4|{r['old_head']}|{r['new_head']}", "title": f"ほかのユーザーの規則の変更（{len(foreign)} 件のコミット）",
            "what": f"GitHub から取り込んだマスターに、ほかのユーザーのコミットが規則・スキルを変えています: {lines}。取り入れると決めるまで、この PC へは配りません。",
            "applies": "、".join(files[:20]), "refs": {"old": r["old_head"], "new": r["new_head"], "commits": foreign, "files": files},
            "options": [{"id": "take", "label": "取り入れる", "primary": True},
                        {"id": "reject", "label": "取り入れない（マスターをこの変更の前に戻す）"}, {"id": "later", "label": "あとで"}]})
    return info, items


def held_files() -> set[str]:
    """判断待ちの J4 が触っているマスターのファイル（決めるまで配らない）。"""
    return {f for i in inbox.items() if i["kind"] == "J4" for f in i["refs"].get("files", [])}


def tool_written() -> list[str]:
    """マスターの中で、いまの中身がツールの書いた中身のままのファイル（マスターの根からの相対パス）。"""
    root = master_root()
    want: dict[str, set[str]] = {}
    for e in changes.events():
        for c in e.get("changes", []):
            p = Path(c["path"])
            try:
                rel = p.resolve().relative_to(root).as_posix()
            except ValueError:
                continue
            h = c["before_hash"] if e.get("undone") else c["after_hash"]
            want.setdefault(rel, set()).add(str(h))
    out = []
    for rel, hs in want.items():
        if str(sha(read(root / rel))) in hs:
            out.append(rel)
    return sorted(out)


def publish_step(summary: str) -> dict[str, Any]:
    st = fleet.status()
    if not st.get("ok"):
        return {"ok": False, "error": st.get("error")}
    dirty = set(st.get("dirty") or [])
    paths = [p for p in tool_written() if p in dirty]
    if not paths:
        return {"ok": True, "commit": None, "files": []}
    return fleet.publish(f"pamgr: 点検で反映（{len(paths)} ファイル）\n\n{summary}"[:4000], paths)


def reject(it: dict[str, Any]) -> dict[str, Any]:
    """ほかのユーザーの変更を取り入れない: そのファイルをマスターで、変更の前の版に戻す（取り消せる）。"""
    root = master_root()
    old = it["refs"]["old"]
    writes = []
    for rel in it["refs"]["files"]:
        r = subprocess.run(["git", "-C", str(root), "show", f"{old}:{rel}"], capture_output=True,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        before = r.stdout if r.returncode == 0 else None
        cur = read(root / rel)
        if before is not None and cur is not None and b"\r\n" in cur and b"\r\n" not in before:
            before = before.replace(b"\n", b"\r\n")      # 作業ツリーの改行の流儀（autocrlf）に合わせる
        if cur != before:
            writes.append(Write(root / rel, before, sha(cur)))
    return changes.commit(Event("decide", "判断: ほかのユーザーの変更を取り入れない", it["title"], "師匠の判断（J4）。マスターを変更の前に戻した",
                                writes, refs={"item_id": it["id"]}))
