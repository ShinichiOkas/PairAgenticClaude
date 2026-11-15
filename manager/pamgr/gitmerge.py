"""分かれた枝のマージ（UC4 の例外フロー）: この PC と GitHub の両方で変わったとき（マスター・ペア固有の層）。

1. git の通常のマージを試す（違うファイル・違う箇所なら、そのまま入る）
2. ぶつかったファイルのうち、規範の文書（.md）は共通の元の版を基準に節ごとにマージする。
   判定の共有ファイル（situations/verdicts.json）は両方を足し合わせる
3. 解けないものが残れば、マージをやめて元に戻し（git merge --abort）、判断待ち J2 に上げる。
   師匠が決めたら「この PC の版を優先」「GitHub の版を優先」（git の -X ours／theirs）でマージし直す
force・rebase・reset はしない。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .fleet import _err, _foreign_commits, _git, _upstream

UNION_JSON = ("situations/verdicts.json",)


def _stage(root: Path, n: int, path: str) -> str | None:
    rc, out, _ = _git(root, "show", f":{n}:{path}")
    return out if rc == 0 else None


def _union_json(ours: str | None, theirs: str | None) -> str | None:
    try:
        a = json.loads(ours) if ours else {}
        b = json.loads(theirs) if theirs else {}
    except json.JSONDecodeError:
        return None
    return dump_lines({**b, **a})


def dump_lines(d: dict[str, Any]) -> str:
    """1 件 1 行の JSON（git が行ごとにマージしやすい）。"""
    rows = [f"{json.dumps(k, ensure_ascii=False)}: {json.dumps(d[k], ensure_ascii=False, sort_keys=True)}" for k in sorted(d)]
    return "{\n" + ",\n".join(rows) + ("\n" if rows else "") + "}\n"


def resolve_file(root: Path, path: str) -> str | None:
    """ぶつかったファイルを自動で解く。解けなければ None。"""
    from .sweep import merge_sections
    base, ours, theirs = _stage(root, 1, path), _stage(root, 2, path), _stage(root, 3, path)
    if path in UNION_JSON:
        return _union_json(ours, theirs)
    if path.endswith(".md") and ours is not None and theirs is not None:
        r = merge_sections(ours, theirs, base if base is not None else "", path)
        return r.text if not r.conflicts else None
    return None


def merge_upstream(root: Path, prefer: str | None = None) -> dict[str, Any]:
    """@{u} をマージして commit する。prefer（"ours"／"theirs"）は判断のあと。解けなければ元に戻して conflicts を返す。"""
    res: dict[str, Any] = {"ok": False, "conflicts": [], "resolved": [], "foreign": [], "changed": []}
    if not _upstream(root):
        res["error"] = "upstream（追跡する遠隔ブランチ）が設定されていない"
        return res
    rc, old, _ = _git(root, "rev-parse", "HEAD")
    rc2, up, _ = _git(root, "rev-parse", "@{u}")
    old, up = old.strip(), up.strip()
    res["old_head"], res["upstream"] = old, up
    args = ["merge", "--no-edit"] + (["-X", prefer] if prefer else []) + ["@{u}"]
    r = _git(root, *args, timeout=180)
    if r[0] != 0:
        rc, out, _ = _git(root, "diff", "--name-only", "--diff-filter=U")
        conflicted = [x.strip() for x in out.splitlines() if x.strip()] if rc == 0 else []
        if not conflicted:
            _abort(root)
            res["error"] = _err(r, "git merge に失敗")
            return res
        unresolved = []
        for p in conflicted:
            text = resolve_file(root, p)
            if text is None:
                unresolved.append(p)
                continue
            (root / p).write_text(text, encoding="utf-8", newline="")
            _git(root, "add", "--", p)
            res["resolved"].append(p)
        if unresolved:
            _abort(root)
            res["conflicts"] = unresolved
            res["error"] = "自動ではマージできない箇所がある"
            return res
        c = _git(root, "commit", "--no-edit", timeout=180)
        if c[0] != 0:
            _abort(root)
            res["error"] = _err(c, "マージの commit に失敗")
            return res
    rc, new, _ = _git(root, "rev-parse", "HEAD")
    res["new_head"] = new.strip()
    rc, out, _ = _git(root, "diff", "--name-only", old, res["new_head"])
    res["changed"] = [x.strip() for x in out.splitlines() if x.strip()] if rc == 0 else []
    res["foreign"] = _foreign_commits(root, old, up)
    res["ok"] = True
    return res


def _abort(root: Path) -> None:
    rc, out, _ = _git(root, "rev-parse", "-q", "--verify", "MERGE_HEAD")
    if rc == 0 and out.strip():
        _git(root, "merge", "--abort")


def push_if_ahead(root: Path) -> dict[str, Any]:
    """upstream より先に進んでいれば push する（マージの commit を GitHub へ）。"""
    up = _upstream(root)
    if not up:
        return {"ok": True, "pushed": False}
    rc, out, _ = _git(root, "rev-list", "--count", "@{u}..HEAD")
    if rc != 0 or not out.strip().isdigit() or int(out.strip()) == 0:
        return {"ok": True, "pushed": False}
    r = _git(root, "push", up["remote"], f"HEAD:refs/heads/{up['branch']}", timeout=180)
    if r[0] != 0:
        return {"ok": False, "pushed": False, "error": _err(r, "git push に失敗")}
    return {"ok": True, "pushed": True}


def conflict_item(repo: str, label: str, root: Path, m: dict[str, Any], inside: tuple[str, ...] | None) -> dict[str, Any]:
    """マージできなかったときの判断待ち（J2）。inside の外のファイル（コードなど）がぶつかったら、手で直してもらう。"""
    files = m.get("conflicts", [])
    outside = [f for f in files if inside is not None and f.split("/")[0] not in inside]
    opts = ([{"id": "later", "label": "あとで（手で git pull して直す）", "primary": True}] if outside else
            [{"id": "ours", "label": "この PC の版を優先してマージ", "primary": True},
             {"id": "theirs", "label": "GitHub の版を優先してマージ"}, {"id": "later", "label": "あとで"}])
    what = (f"{label}が、この PC と GitHub の両方で変わっていて、自動ではマージできませんでした（ぶつかった所: {'、'.join(files[:8])}）。"
            + (f" 規則の外のファイル（{'、'.join(outside[:5])}）もぶつかっているので、手で直してください。" if outside else
               " どちらを優先するか選ぶと、ぶつかった箇所だけその版にしてマージし、push します。"))
    return {"kind": "J2", "key": f"J2git|{repo}|{m.get('old_head', '')}|{m.get('upstream', '')}",
            "title": f"{label}の git の衝突", "what": what, "applies": "、".join(files[:20]),
            "refs": {"git": repo, "root": str(root), "files": files, "outside": outside}, "options": opts}
