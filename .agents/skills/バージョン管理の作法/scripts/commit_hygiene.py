#!/usr/bin/env python3
"""git status から、未コミット・未追跡の残り、コミットの意図の混在、生成物と正典のずれ、生成物の「手で編集しない」表示の欠けを検査する（読むだけ）。

入力: `git status --porcelain` の出力（標準入力 / --status-file）か、--repo でリポジトリを指す（git status を読むだけで実行する）。
検査:
  clean か（未追跡 ?? も数える。status が clean に見えても untracked は残る）
  変更を最上位ディレクトリで束ね、--max-groups を超えたら「1 コミット 1 意図」が崩れている疑いとして分割案を出す
  --gen-map map.json（{"生成物パス": "正典パス"}）: 片方だけ変更されていれば指摘（同じコミットに入れる）
  --generated パス...: 先頭 10 行に「手で編集しない」（または DO NOT EDIT）が無ければ指摘
LLM・ネットワークは呼ばない。git は status しか呼ばず、何も書き込まない。clean でない／指摘があれば終了コード 1。

使い方:
  python commit_hygiene.py --repo . --gen-map gen.json --generated docs/roles-coding.md
  git status --porcelain | python commit_hygiene.py
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True

NO_EDIT = re.compile(r"手で編集しない|手で直さない|DO NOT EDIT|do not edit|auto-?generated", re.I)


def unquote(p: str) -> str:
    """git が引用符で囲んだパス（日本語などを 8 進エスケープで出す）を元に戻す。"""
    if not (len(p) >= 2 and p[0] == '"' and p[-1] == '"'):
        return p
    simple = {"n": b"\n", "t": b"\t", '"': b'"', "\\": b"\\"}
    buf = bytearray()
    for m in re.finditer(r"\\([0-7]{3})|\\(.)|([^\\]+)", p[1:-1], re.S):
        if m.group(1):
            buf.append(int(m.group(1), 8))
        elif m.group(2):
            buf.extend(simple.get(m.group(2), m.group(2).encode()))
        else:
            buf.extend(m.group(3).encode("utf-8"))
    return buf.decode("utf-8", errors="replace")


def parse_porcelain(text: str) -> list[dict]:
    entries = []
    for line in text.splitlines():
        if len(line) < 4:
            continue
        xy, rest = line[:2], line[3:]
        if " -> " in rest:
            rest = rest.split(" -> ", 1)[1]
        path = unquote(rest.strip()).replace("\\", "/")
        if xy == "??":
            state = "untracked"
        elif "U" in xy or xy in ("AA", "DD"):
            state = "conflict"
        elif xy[0] != " ":
            state = "staged" if xy[1] == " " else "staged+unstaged"
        else:
            state = "unstaged"
        entries.append({"path": path, "xy": xy, "state": state})
    return entries


def group_of(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "(root)"


def analyze(entries: list[dict], max_groups: int = 3, gen_map: dict | None = None,
            generated_check: dict[str, str] | None = None) -> dict:
    """generated_check: {パス: 先頭 10 行の本文}。"""
    problems: list[str] = []
    by_state: dict[str, list[str]] = {}
    for e in entries:
        by_state.setdefault(e["state"], []).append(e["path"])
    groups: dict[str, list[str]] = {}
    for e in entries:
        groups.setdefault(group_of(e["path"]), []).append(e["path"])
    clean = not entries
    if "untracked" in by_state:
        problems.append(f"未追跡 {len(by_state['untracked'])} 件が残っている（status が clean に見えても残る）")
    if "conflict" in by_state:
        problems.append(f"衝突 {len(by_state['conflict'])} 件")
    if len(groups) > max_groups:
        problems.append(f"変更が {len(groups)} 群にまたがる（上限 {max_groups}）。1 コミット 1 意図に分ける")
    changed = {e["path"] for e in entries}
    for gen, src in (gen_map or {}).items():
        g, s = gen in changed, src in changed
        if g and not s:
            problems.append(f"生成物 {gen} だけが変わっている（正典 {src} は未変更。生成物を手で直していないか）")
        elif s and not g:
            problems.append(f"正典 {src} だけが変わっている（生成物 {gen} を再生成して同じコミットに入れる）")
    for path, head in (generated_check or {}).items():
        if head is None:
            problems.append(f"生成物 {path} が読めない")
        elif not NO_EDIT.search(head):
            problems.append(f"生成物 {path} に「手で編集しない」の表示が無い")
    plan = [{"group": g, "files": sorted(fs)} for g, fs in sorted(groups.items())]
    return {"clean": clean, "counts": {k: len(v) for k, v in sorted(by_state.items())},
            "split_plan": plan, "problems": problems}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--repo", help="リポジトリのパス（git status を実行する）")
    ap.add_argument("--status-file", help="git status --porcelain の出力ファイル（省略時は標準入力）")
    ap.add_argument("--max-groups", type=int, default=3)
    ap.add_argument("--gen-map", help="生成物->正典 の JSON")
    ap.add_argument("--generated", nargs="*", default=[], help="「手で編集しない」表示を確かめる生成物")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if a.repo:
        r = subprocess.run(["git", "-C", a.repo, "-c", "core.quotepath=false", "status", "--porcelain"],
                           capture_output=True, text=True, encoding="utf-8")
        if r.returncode != 0:
            print(f"git status に失敗: {r.stderr.strip()}", file=sys.stderr)
            return 2
        text = r.stdout
        root = Path(a.repo)
    else:
        text = Path(a.status_file).read_text(encoding="utf-8") if a.status_file else sys.stdin.read()
        root = Path(".")
    gen_map = json.loads(Path(a.gen_map).read_text(encoding="utf-8")) if a.gen_map else None
    gen_check = {}
    for g in a.generated:
        p = root / g
        gen_check[g] = "\n".join(p.read_text(encoding="utf-8", errors="replace").splitlines()[:10]) if p.is_file() else None
    res = analyze(parse_porcelain(text), a.max_groups, gen_map, gen_check)
    if a.json:
        print(json.dumps(res, ensure_ascii=False, indent=2))
    else:
        print("作業ツリー: " + ("clean" if res["clean"] else "未コミットあり " + str(res["counts"])))
        if not res["clean"]:
            print("## 分割案（最上位ディレクトリ単位・意図で切り直すこと）")
            for g in res["split_plan"]:
                print(f"- {g['group']}: {len(g['files'])} 件")
        for p in res["problems"]:
            print(f"! {p}")
    return 0 if res["clean"] and not res["problems"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
