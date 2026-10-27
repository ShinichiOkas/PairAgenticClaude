#!/usr/bin/env python3
"""探針の前後でディレクトリの指紋を取って差分を出し、成果物への書き込みを検出し、作業空間に残った探針の産物を捨てる。

サブコマンド:
  snapshot  探針の前に、ディレクトリ内の全ファイルの SHA-256 を JSON に保存する（--out は新規のみ・上書きしない）
  check     探針の後に、新規／変更／削除を列挙する。--protect 配下（成果物）の変化、--workspace の外の変化は違反
            違反でない変化は「測定条件に申告する副作用」として出す（復元はしない）
  discard   --workspace 内の「探針が作った新規ファイル」だけを捨てる。既定は下見、削除は --apply のとき
            変更・削除されたファイルや workspace 外には触らない

使い方:
  python probe_scope.py snapshot --root . --out before.json
  python probe_scope.py check --root . --snapshot before.json --workspace .probe --protect src
  python probe_scope.py discard --root . --snapshot before.json --workspace .probe --apply
.git と __pycache__ は見ない。LLM・ネットワークは呼ばない。check は違反があれば終了コード 1。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True

SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", "node_modules"}


def fingerprint(root: Path) -> dict[str, str]:
    out = {}
    for f in sorted(root.rglob("*")):
        if not f.is_file():
            continue
        rel = f.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        out[rel.as_posix()] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


def diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "new": sorted(set(after) - set(before)),
        "modified": sorted(p for p in set(before) & set(after) if before[p] != after[p]),
        "deleted": sorted(set(before) - set(after)),
    }


def under(path: str, prefix: str) -> bool:
    prefix = prefix.strip("/").replace("\\", "/")
    return path == prefix or path.startswith(prefix + "/")


def evaluate(d: dict[str, list[str]], workspace: str | None, protect: list[str]) -> dict:
    violations, side_effects = [], []
    for kind, paths in d.items():
        for p in paths:
            if any(under(p, pr) for pr in protect):
                violations.append({"path": p, "kind": kind, "reason": "成果物（--protect）への書き込み"})
            elif workspace is not None and not under(p, workspace):
                violations.append({"path": p, "kind": kind, "reason": "作業空間（--workspace）の外への書き込み"})
            else:
                side_effects.append({"path": p, "kind": kind})
    return {"violations": violations, "declare_as_side_effects": side_effects, "diff": d}


def load_snapshot(path: str) -> dict[str, str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["files"]


def cmd_snapshot(a) -> int:
    out = Path(a.out)
    if out.exists():
        print(f"既にある。上書きしない: {out}", file=sys.stderr)
        return 2
    root = Path(a.root)
    try:
        out.resolve().relative_to(root.resolve())
        print("--out は root の外に置く（指紋ファイル自身が差分に出るため）", file=sys.stderr)
        return 2
    except ValueError:
        pass
    snap = {"root": root.resolve().as_posix(), "files": fingerprint(root)}
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=1, sort_keys=True), encoding="utf-8")
    print(f"指紋 {len(snap['files'])} 件を {out} に保存")
    return 0


def cmd_check(a) -> int:
    res = evaluate(diff(load_snapshot(a.snapshot), fingerprint(Path(a.root))), a.workspace, a.protect or [])
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        d = res["diff"]
        print(f"新規 {len(d['new'])} / 変更 {len(d['modified'])} / 削除 {len(d['deleted'])} / 違反 {len(res['violations'])}")
        for v in res["violations"]:
            print(f"! [{v['kind']}] {v['path']}  ({v['reason']})")
        if res["declare_as_side_effects"]:
            print("## 測定条件に申告する副作用（復元はしない）")
            for s in res["declare_as_side_effects"]:
                print(f"- [{s['kind']}] {s['path']}")
    return 1 if res["violations"] else 0


def cmd_discard(a) -> int:
    root = Path(a.root).resolve()
    ws = (root / a.workspace).resolve()
    try:
        ws.relative_to(root)
    except ValueError:
        print("workspace は root の中であること", file=sys.stderr)
        return 2
    if ws == root:
        print("workspace に root 全体は指定できない", file=sys.stderr)
        return 2
    d = diff(load_snapshot(a.snapshot), fingerprint(root))
    ws_rel = ws.relative_to(root).as_posix()
    targets = [p for p in d["new"] if under(p, ws_rel)]
    untouched = [p for k in ("modified", "deleted") for p in d[k]] + [p for p in d["new"] if p not in targets]
    for p in targets:
        print(f"{'削除' if a.apply else '削除予定'}: {p}")
        if a.apply:
            (root / p).unlink()
    if a.apply:  # 探針が作って空になったディレクトリも片付ける（workspace 自体は残す）
        for dpath in sorted((x for x in ws.rglob("*") if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
            if not any(dpath.iterdir()):
                dpath.rmdir()
    if untouched:
        print("## 触れなかった変化（変更・削除、または workspace 外の新規）")
        for p in untouched:
            print(f"- {p}")
    if not a.apply:
        print("（下見のみ。捨てるには --apply）")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("snapshot")
    s.add_argument("--root", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_snapshot)
    c = sub.add_parser("check")
    c.add_argument("--root", required=True)
    c.add_argument("--snapshot", required=True)
    c.add_argument("--workspace", help="探針の産物を置いてよい場所（root からの相対）")
    c.add_argument("--protect", nargs="*", help="書き込まれてはならない成果物のパス（root からの相対）")
    c.add_argument("--json", action="store_true")
    c.set_defaults(fn=cmd_check)
    d = sub.add_parser("discard")
    d.add_argument("--root", required=True)
    d.add_argument("--snapshot", required=True)
    d.add_argument("--workspace", required=True)
    d.add_argument("--apply", action="store_true")
    d.set_defaults(fn=cmd_discard)
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())
