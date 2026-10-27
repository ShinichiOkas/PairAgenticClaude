#!/usr/bin/env python3
"""スプリントのジャーナル／作業ツリーごとのポインタの作成・状態遷移・食い違い検出・旧形式からの移設を決定的に行う。

使い方:
  python sprint_ops.py [--project X] key                    # 作業ツリーの鍵（正本: SHA-1(ホスト名+toplevel を区切りなしで連結, UTF-8) の先頭 8 桁。
                                                            #   ホスト名は socket.gethostname() の値で大文字小文字そのまま、toplevel は git の出力のまま前後の空白を除く）
  python sprint_ops.py status                               # ポインタとジャーナルの status を突き合わせる。規則の違う鍵のポインタも報告（無ければ 0、有れば 5）
  python sprint_ops.py start --goal "ログイン修正" --apply  # ジャーナル+ポインタ作成（status=deliberating）
  python sprint_ops.py transition --to executing --apply    # 両方の status を更新（不正な遷移は拒否）
  python sprint_ops.py migrate --apply                      # 規則の違う鍵のポインタを正本の鍵へ付け替え＋旧 current-sprint.json を新方式へ移設（閉じたスプリントは写さない）

既定は下見。書き込みは --apply のときだけ。食い違ったらジャーナルを正とする。
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import socket
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:
        pass

# 協議 -> 合意 -> 実行 -> 振り返り -> 完了。差し戻しは実行中にいつでも協議へ。
# 要求が明確なときは合意を飛ばして実行へ進める（「言われなくても進める」）。
TRANSITIONS = {
    "deliberating": {"agreed", "executing"},
    "agreed": {"executing", "deliberating"},
    "executing": {"deliberating", "retrospecting"},
    "retrospecting": {"completed", "deliberating"},
    "completed": set(),
}
CLOSED_AGREEMENT = {"completed", "closed", "done"}


def toplevel(project: Path, override: str) -> str:
    if override:
        return override
    try:
        r = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        return r.stdout.strip()
    except Exception:
        return str(project.resolve())


def worktree_key(host: str, top: str) -> str:
    """正本の規則: socket.gethostname() の値（大文字小文字そのまま）と git rev-parse --show-toplevel の出力
    （そのまま・前後の空白を除く）を区切りなしで連結し、UTF-8 で SHA-1、16 進の先頭 8 文字。"""
    return hashlib.sha1((host + top.strip()).encode("utf-8")).hexdigest()[:8]


def legacy_variant_keys(host: str, top: str) -> dict:
    """過去に実装が割れていた鍵の計算（区切り・大文字小文字・パス表記）で、このマシン・この作業ツリーのものを列挙する。
    鍵 -> 変種の説明。正本の鍵は含めない。"""
    top = top.strip()
    canon = worktree_key(host, top)
    out: dict = {}
    for hn, hv in (("ホスト名そのまま", host), ("ホスト名小文字", host.lower())):
        for tn, tv in (("パスそのまま", top), ("パス小文字", top.lower()), ("パス\区切り", top.replace("/", "\\"))):
            for sn, sv in (("区切りなし", ""), ("|区切り", "|"), (":区切り", ":"), ("/区切り", "/"), ("-区切り", "-"), ("空白区切り", " ")):
                k = hashlib.sha1((hv + sv + tv).encode("utf-8")).hexdigest()[:8]
                if k != canon:
                    out.setdefault(k, f"{hn}+{sn}+{tn}")
    return out


def foreign_pointers(pa: Path, host: str, top: str) -> list:
    """current/ の中で、鍵が正本と一致しないポインタ。(path, 鍵, 変種の説明 or None, 中身 or None, エラー or None)"""
    cur = pa / "current"
    canon = worktree_key(host, top)
    variants = legacy_variant_keys(host, top)
    res = []
    if not cur.is_dir():
        return res
    for f in sorted(cur.glob("*.json")):
        k = f.name.split("-", 1)[0]
        if k == canon:
            continue
        try:
            body, err = read_json(f), None
        except Exception as e:  # noqa: BLE001
            body, err = None, str(e)
        res.append((f, k, variants.get(k), body, err))
    return res


def ctx(a):
    project = Path(a.project).resolve()
    host = a.host or socket.gethostname()
    top = toplevel(project, a.toplevel)
    key = worktree_key(host, top)
    pointer = project / ".pair-agent" / "current" / f"{key}-{Path(top).name}.json"
    return project, host, top, key, pointer


def now_iso(a) -> str:
    return a.now or datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s[:40]


def read_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def write_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")


def set_agreement_status(path: Path, status: str, ts: str) -> bool:
    if not path.is_file():
        return False
    t = path.read_text(encoding="utf-8")
    if not re.search(r"^status:\s*", t, re.M):
        return False
    t = re.sub(r"^status:.*$", f"status: {status}", t, count=1, flags=re.M)
    t = re.sub(r"^updated_at:.*$", f"updated_at: {ts}", t, count=1, flags=re.M)
    path.write_text(t, encoding="utf-8", newline="\n")
    return True


def cmd_key(a) -> int:
    project, host, top, key, pointer = ctx(a)
    print(f"host={host}\ntoplevel={top}\nkey={key}\npointer={pointer}")
    return 0


def cmd_status(a) -> int:
    project, host, top, key, pointer = ctx(a)
    rc = status_main(project, pointer)
    foreign = foreign_pointers(project / ".pair-agent", host, top)
    for f, k, variant, body, err in foreign:
        if err:
            print(f"規則の違う鍵: {f.name}（鍵 {k} / 正本 {key}）読めない: {err}")
            continue
        b = body or {}
        who = f"変種={variant}（このマシン由来。migrate で移せる）" if variant else "どの変種とも一致しない（別 PC 由来の可能性。自動では移さない）"
        print(f"規則の違う鍵: {f.name}（鍵 {k} / 正本 {key}）{who}"
              f" -> sprint_id={b.get('sprint_id')} status={b.get('status')} journal={b.get('journal')}")
    if foreign and rc == 0:
        return 5
    return rc


def status_main(project: Path, pointer: Path) -> int:
    if not pointer.is_file():
        print(f"ポインタ無し: {pointer}")
        legacy = project / ".pair-agent" / "current-sprint.json"
        if legacy.is_file():
            print("旧形式 current-sprint.json が有る -> `migrate` の対象")
        return 1
    ptr = read_json(pointer)
    jpath = project / ptr.get("journal", "")
    print(f"pointer: {pointer.name} status={ptr.get('status')} sprint_id={ptr.get('sprint_id')}")
    if not jpath.is_file():
        print(f"ERROR: ジャーナルが無い: {jpath}")
        return 2
    j = read_json(jpath)
    print(f"journal: {jpath.name} status={j.get('status')} goal={j.get('goal')}")
    if j.get("status") != ptr.get("status"):
        print(f"MISMATCH: ポインタ={ptr.get('status')} / ジャーナル={j.get('status')}（ジャーナルが正。transition で直す）")
        return 3
    print("OK: 一致")
    return 0


def cmd_start(a) -> int:
    project, host, top, key, pointer = ctx(a)
    ts = now_iso(a)
    sid = a.sprint_id or f"{ts[:10].replace('-', '')}-{slug(a.goal) or hashlib.sha1(a.goal.encode()).hexdigest()[:8]}"
    journal_rel = f".pair-agent/sprints/{sid}.json"
    jpath = project / journal_rel
    if jpath.exists():
        print(f"ERROR: ジャーナルが既に有る（上書きしない）: {jpath}", file=sys.stderr)
        return 3
    journal = {
        "sprint_id": sid, "status": "deliberating", "goal": a.goal, "created_at": ts,
        "agreement_path": f".pair-agent/agreements/{slug(a.goal) or sid}.md", "経過": [],
    }
    ptr = {"workcopy": {"host": host, "path": top, "key": key}, "sprint_id": sid,
           "status": "deliberating", "journal": journal_rel, "updated_at": ts}
    if not a.apply:
        print(f"[下見] ジャーナル {jpath}\n[下見] ポインタ {pointer}\n{json.dumps(journal, ensure_ascii=False, indent=2)}")
        return 0
    write_json(jpath, journal)
    write_json(pointer, ptr)
    print(f"開始: {sid}\n  {jpath}\n  {pointer}")
    return 0


def cmd_transition(a) -> int:
    project, host, top, key, pointer = ctx(a)
    if not pointer.is_file():
        print(f"ERROR: ポインタ無し: {pointer}", file=sys.stderr)
        return 2
    ptr = read_json(pointer)
    jpath = project / ptr["journal"]
    if not jpath.is_file():
        print(f"ERROR: ジャーナルが無い: {jpath}", file=sys.stderr)
        return 2
    j = read_json(jpath)
    cur = j.get("status")  # ジャーナルが正
    if cur not in TRANSITIONS:
        print(f"ERROR: ジャーナルの status が不正: {cur!r}", file=sys.stderr)
        return 2
    if a.to not in TRANSITIONS[cur] and a.to != cur:
        print(f"ERROR: {cur} -> {a.to} は許されない（許可: {sorted(TRANSITIONS[cur]) or 'なし'}）", file=sys.stderr)
        return 3
    ts = now_iso(a)
    if not a.apply:
        print(f"[下見] {cur} -> {a.to}（ジャーナル {jpath.name} とポインタ {pointer.name} の両方）")
        return 0
    j["status"] = a.to
    j.setdefault("経過", []).append({"at": ts, "status": f"{cur} -> {a.to}", "note": a.note})
    ptr["status"] = a.to
    ptr["updated_at"] = ts
    write_json(jpath, j)
    write_json(pointer, ptr)
    msg = f"遷移: {cur} -> {a.to}"
    if a.to in ("executing", "deliberating", "agreed", "completed") and j.get("agreement_path"):
        if set_agreement_status(project / j["agreement_path"], a.to, ts):
            msg += "（合意ドキュメントの status も更新）"
    print(msg)
    return 0


def rekey_pointers(a, pa: Path, host: str, top: str, key: str) -> int:
    """規則の違う鍵のポインタを正本の鍵の名前へ移す。既定は下見。移す先が既に有れば止めて報告（4）。"""
    foreign = foreign_pointers(pa, host, top)
    if not foreign:
        return 0
    plan, blocked = [], []
    for f, k, variant, body, err in foreign:
        if not variant:
            print(f"対象外: {f.name} は鍵 {k} がどの変種とも一致しない（別 PC 由来の可能性。移さない）")
            continue
        dest = f.with_name(f"{key}-{f.name.split('-', 1)[1]}" if "-" in f.name else f"{key}.json")
        if dest.exists():
            blocked.append(f"{f.name} -> {dest.name}（移す先が既に有る）")
        else:
            plan.append((f, dest, k, variant, body))
    if blocked:
        print("NEEDS-DECISION: 移す先が既に有る。何も移さない: " + " / ".join(blocked))
        return 4
    for f, dest, k, variant, body in plan:
        if not a.apply:
            print(f"[下見] 鍵の付け替え: {f.name} -> {dest.name}（変種={variant}）")
            continue
        if isinstance(body, dict):
            if isinstance(body.get("workcopy"), dict):
                body["workcopy"]["key"] = key
            write_json(dest, body)
            f.unlink()
        else:
            f.rename(dest)
        print(f"付け替えた: {f.name} -> {dest.name}")
    return 0


def cmd_migrate(a) -> int:
    project, host, top, key, pointer = ctx(a)
    pa = project / ".pair-agent"
    rc = rekey_pointers(a, pa, host, top, key)
    if rc:
        return rc
    legacy = pa / "current-sprint.json"
    if not legacy.is_file():
        print("移設対象なし（current-sprint.json が無い）")
        return 0
    old = read_json(legacy)
    if old.get("status") == "moved" or "_moved" in old:
        print("移設済み（道標になっている）")
        return 0
    if (pa / "current").is_dir() and any((pa / "current").glob("*.json")):
        print("移設済み（current/ にポインタが有る）")
        return 0
    sid = old.get("sprint_id")
    if not sid:
        sid = f"{(old.get('created_at') or now_iso(a))[:10].replace('-', '')}-{slug(old.get('goal', '')) or 'legacy'}"
    jpath = pa / "sprints" / f"{sid}.json"
    # 手順 0: 閉じた記録を古い中身で上書きしない
    reasons = []
    if jpath.exists():
        reasons.append(f"ジャーナル {jpath.name} が既に有る")
    ag = pa / "agreements"
    if ag.is_dir():
        for f in sorted(ag.glob("*.md")):
            m = re.search(r"^status:\s*(\S+)", f.read_text(encoding="utf-8", errors="replace"), re.M)
            if m and m.group(1) in CLOSED_AGREEMENT and sid in f.read_text(encoding="utf-8", errors="replace"):
                reasons.append(f"合意 {f.name} が {m.group(1)}")
    if reasons:
        print("NEEDS-DECISION: 写さない。ポインタをどのスプリントに向けるか師匠に聞く: " + " / ".join(reasons))
        return 4
    ts = now_iso(a)
    journal = dict(old)
    journal["sprint_id"] = sid
    journal.setdefault("経過", [])
    ptr = {"workcopy": {"host": host, "path": top, "key": key}, "sprint_id": sid,
           "status": old.get("status", "deliberating"), "journal": f".pair-agent/sprints/{sid}.json", "updated_at": ts}
    signpost = {"_moved": "現在地は .pair-agent/current/<鍵>.json（作業ツリーごと）、経過は "
                          f".pair-agent/sprints/{sid}.json。CLAUDE.md『スプリントの現在地は作業ツリーごと』を読むこと",
                "status": "moved"}
    if not a.apply:
        print(f"[下見] {legacy.name} -> ジャーナル {jpath}、ポインタ {pointer}、道標に置換")
        return 0
    write_json(jpath, journal)
    write_json(pointer, ptr)
    write_json(legacy, signpost)
    print(f"移設した: {sid}")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--project", default=".", help="プロジェクトルート（.pair-agent を含む）")
    p.add_argument("--host", default="", help="ホスト名（テスト用。既定は実ホスト名）")
    p.add_argument("--toplevel", default="", help="git toplevel の上書き（テスト用）")
    p.add_argument("--now", default="", help="タイムスタンプ固定（テスト用）")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("key")
    sub.add_parser("status")
    s = sub.add_parser("start")
    s.add_argument("--goal", required=True)
    s.add_argument("--sprint-id", default="")
    s.add_argument("--apply", action="store_true")
    t = sub.add_parser("transition")
    t.add_argument("--to", required=True, choices=list(TRANSITIONS))
    t.add_argument("--note", default="")
    t.add_argument("--apply", action="store_true")
    m = sub.add_parser("migrate")
    m.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    return {"key": cmd_key, "status": cmd_status, "start": cmd_start,
            "transition": cmd_transition, "migrate": cmd_migrate}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
