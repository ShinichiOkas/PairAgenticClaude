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

from . import changes, fleet, gitmerge, inbox, settings
from .changes import Event, Write, read, sha
from .fleet import _err, _git
from .paths import master_root, user_home

VERDICTS_SHARED = "situations/verdicts.json"
PAIR_REMOTE = "pamgr-sync"


def pull_step() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    r = fleet.pull()
    items: list[dict[str, Any]] = []
    if not r.get("ok") and r.get("diverged"):          # この PC と GitHub の両方で変わった → マージ（節ごと）
        m = gitmerge.merge_upstream(master_root())
        if m["ok"]:
            r = {"ok": True, "old_head": m["old_head"], "new_head": m["new_head"], "changed": m["changed"],
                 "foreign": m["foreign"], "merged": True, "resolved": m["resolved"]}
        else:
            r["merge_error"] = m.get("error")
            if m.get("conflicts"):
                items.append(gitmerge.conflict_item("master", "マスター", master_root(), m, fleet.TOOL_PATHS))
    info = {k: r.get(k) for k in ("ok", "old_head", "new_head", "error", "diverged", "merged", "resolved", "merge_error")}
    info["changed"] = len(r.get("changed") or [])
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


def tool_writers() -> dict[str, dict[str, Any]]:
    """マスターの中で、いまの中身がツールの書いた中身のままのファイル → それを書いた出来事（最後のもの）。"""
    root = master_root()
    want: dict[str, dict[str, dict[str, Any]]] = {}
    for e in changes.events():
        for c in e.get("changes", []):
            p = Path(c["path"])
            try:
                rel = p.resolve().relative_to(root).as_posix()
            except ValueError:
                continue
            h = c["before_hash"] if e.get("undone") else c["after_hash"]
            want.setdefault(rel, {})[str(h)] = e
    out: dict[str, dict[str, Any]] = {}
    for rel, hs in want.items():
        e = hs.get(str(sha(read(root / rel))))
        if e is not None:
            out[rel] = e
    return dict(sorted(out.items()))


def tool_written() -> list[str]:
    """マスターの中で、いまの中身がツールの書いた中身のままのファイル（マスターの根からの相対パス）。"""
    return list(tool_writers())


def publish_step(summary: str) -> dict[str, Any]:
    st = fleet.status()
    if not st.get("ok"):
        return {"ok": False, "error": st.get("error")}
    dirty = set(st.get("dirty") or [])
    writers = tool_writers()
    paths = [p for p in writers if p in dirty] + ([VERDICTS_SHARED] if VERDICTS_SHARED in dirty else [])
    res: dict[str, Any] = {"ok": True, "commit": None, "files": []}
    if paths:
        # 本文には、この点検の出来事だけでなく、入れるファイルと、それを書いた出来事を全部書く
        # （前の判断・取り込みで書いたファイルも入るため。6378f12 は本文に無いファイルを入れていた）
        files = "\n".join(f"- {p}" + (f"（{writers[p].get('what', '')}: {writers[p].get('detail', '')}・{writers[p].get('at', '')}）"
                                      if p in writers else "（判定の共有）") for p in paths)
        res = fleet.publish(f"pamgr: 点検で反映（{len(paths)} ファイル）\n\n入れたファイル:\n{files}\n\nこの点検でやったこと:\n{summary}"[:4000], paths)
    if res.get("ok") and not res.get("pushed"):          # マージの commit など、先に進んだ分を push する
        pr = gitmerge.push_if_ahead(master_root())
        res["pushed"] = pr.get("pushed", False)
        if not pr.get("ok"):
            res.update(ok=False, error=pr.get("error"))
    return res


# ---------------------------------------------------------------- ペア固有の層（~/.claude/pair-agent）の同期（師匠が選ぶ）
def pair_root() -> Path:
    return user_home() / ".claude" / "pair-agent"


def pair_step() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """ペア固有の層を、師匠が選んだ自分のリポジトリと同期する（設定が空なら何もしない）。
    ローカルの変更を自動で commit → fetch → マージ（.md は節ごと）→ push。ぶつかって解けなければ J2。"""
    url = str(settings.get().get("pair_sync_url") or "").strip()
    if not url:
        return {"enabled": False}, []
    root = pair_root()
    if not (root / ".git").exists():
        return {"enabled": True, "ok": False, "error": f"git のリポジトリではない: {root}"}, []
    rc, cur, _ = _git(root, "remote", "get-url", PAIR_REMOTE)
    if rc != 0:
        _git(root, "remote", "add", PAIR_REMOTE, url)
    elif cur.strip() != url:
        _git(root, "remote", "set-url", PAIR_REMOTE, url)
    _git(root, "add", "-A")
    rc, out, _ = _git(root, "diff", "--cached", "--name-only")
    committed = [x for x in out.splitlines() if x.strip()]
    if committed:
        c = _git(root, "commit", "-m", f"pamgr: ペア固有の層の自動コミット（{len(committed)} ファイル）")
        if c[0] != 0:
            return {"enabled": True, "ok": False, "error": _err(c, "commit に失敗")}, []
    f = _git(root, "fetch", PAIR_REMOTE, timeout=180)
    if f[0] != 0:
        return {"enabled": True, "ok": False, "error": _err(f, "fetch に失敗"), "committed": len(committed)}, []
    rc, branch, _ = _git(root, "symbolic-ref", "--short", "-q", "HEAD")
    branch = branch.strip() or "master"
    remote_ref = f"{PAIR_REMOTE}/{branch}"
    has_remote = _git(root, "rev-parse", "-q", "--verify", remote_ref)[0] == 0
    info: dict[str, Any] = {"enabled": True, "ok": True, "committed": len(committed)}
    if not has_remote:                                     # 空のリポジトリ: 初めて押し出す
        p = _git(root, "push", "-u", PAIR_REMOTE, f"HEAD:refs/heads/{branch}", timeout=180)
        info.update(ok=p[0] == 0, pushed=p[0] == 0, first=True)
        if p[0] != 0:
            info["error"] = _err(p, "push に失敗")
        return info, []
    _git(root, "branch", f"--set-upstream-to={remote_ref}")
    if _git(root, "merge-base", "HEAD", remote_ref)[0] != 0:
        return {**info, "ok": False, "error": "同期先の履歴が、この PC のペア固有の層とつながっていません。空のリポジトリか、この層から作ったリポジトリを指定してください"}, []
    items: list[dict[str, Any]] = []
    rc, out, _ = _git(root, "rev-list", "--left-right", "--count", "HEAD...@{u}")
    a, b = (out.split() + ["0", "0"])[:2]
    if b.isdigit() and int(b) > 0:
        m = gitmerge.merge_upstream(root)
        info["pulled"] = m.get("ok", False)
        info["resolved"] = m.get("resolved", [])
        if not m["ok"]:
            info.update(ok=False, error=m.get("error"))
            if m.get("conflicts"):
                items.append(gitmerge.conflict_item("pair", "ペア固有の層", root, m, None))
            return info, items
    pr = gitmerge.push_if_ahead(root)
    info["pushed"] = pr.get("pushed", False)
    if not pr.get("ok"):
        info.update(ok=False, error=pr.get("error"))
    return info, items


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
