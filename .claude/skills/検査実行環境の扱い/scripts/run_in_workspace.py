#!/usr/bin/env python
"""実行可能物を作業空間へ複製し、そこでコマンドを動かして、成果物の場所が無傷か・作業空間に何が書かれたかを報告する。

    python run_in_workspace.py SRC_DIR -- python -m pytest -q            # 下見（何もコピー・実行しない）
    python run_in_workspace.py SRC_DIR --apply -- python -m pytest -q    # 複製して実行

  --workdir DIR   複製先（無い or 空のディレクトリ）。省くと一時ディレクトリを作る。既存ファイルは上書きしない
  --timeout SEC   コマンドの制限時間（既定 600）
  --json          報告を JSON で出す
報告に載るもの: 実施条件（コマンド・作業空間・exit code・Python/OS）／ 成果物の場所の前後差分（あれば違反）／
  作業空間の差分（pytest キャッシュ等の副産物を含む）。復元はしない（何が起きたか分からなくなる）。
検出できないもの: 作業領域に閉じない副作用（実行環境の状態変化・外部通信・共有キャッシュ）。報告の「申告」欄に必ず残る。
終了コード: 0 = 成果物の場所は無傷 ／ 1 = 成果物の場所が書き換わった ／ 2 = 入力不正
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tree_diff  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass


def tail(s: str, n: int = 15) -> str:
    return "\n".join(s.splitlines()[-n:])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="作業空間へ複製して実行し、前後差分を報告する（既定は下見）")
    ap.add_argument("src")
    ap.add_argument("--workdir")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--json", action="store_true")
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd: list[str] = []
    if "--" in argv:  # -- の後ろは丸ごと実行するコマンド（argparse に触らせない）
        k = argv.index("--")
        argv, cmd = argv[:k], argv[k + 1:]
    a = ap.parse_args(argv)
    if not cmd:
        print("エラー: -- の後ろに実行するコマンドを書くこと", file=sys.stderr)
        return 2
    src = os.path.abspath(a.src)
    if not os.path.isdir(src):
        print(f"エラー: {src} はディレクトリではない", file=sys.stderr)
        return 2
    wd = None
    if a.workdir:
        wd = os.path.abspath(a.workdir)
        if os.path.exists(wd) and (not os.path.isdir(wd) or os.listdir(wd)):
            print(f"エラー: {wd} は空のディレクトリではない（上書きしない）", file=sys.stderr)
            return 2
        if wd == src or wd.startswith(src + os.sep) or src.startswith(wd + os.sep):
            print("エラー: 作業空間は成果物の場所と入れ子にできない", file=sys.stderr)
            return 2
    before_src = tree_diff.snapshot(src)
    if not a.apply:
        print("下見（--apply で実行）")
        print(f"  成果物の場所: {src}（{len(before_src)} 件）")
        print(f"  作業空間: {wd or '一時ディレクトリを新規作成'}")
        print(f"  コマンド: {' '.join(cmd)}")
        return 0
    if wd is None:
        wd = tempfile.mkdtemp(prefix="workspace-")
    shutil.copytree(src, wd, dirs_exist_ok=True, symlinks=True)
    before_ws = tree_diff.snapshot(wd)
    timed_out, code, out, err = False, None, "", ""
    try:
        r = subprocess.run(cmd, cwd=wd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=a.timeout)
        code, out, err = r.returncode, r.stdout, r.stderr
    except subprocess.TimeoutExpired as e:
        timed_out = True
        out = (e.stdout.decode("utf-8", "replace") if isinstance(e.stdout, bytes) else e.stdout) or ""
    except OSError as e:
        code, err = 127, str(e)
    src_diff = tree_diff.compare(before_src, tree_diff.snapshot(src))
    ws_diff = tree_diff.compare(before_ws, tree_diff.snapshot(wd))
    report = {
        "実施条件": {"command": cmd, "workspace": wd, "source": src, "exit_code": code, "timed_out": timed_out,
                  "python": sys.version.split()[0], "os": platform.platform()},
        "成果物の場所の差分": src_diff, "作業空間の差分": ws_diff,
        "申告": "作業領域に閉じない副作用（環境の状態変化・外部通信・共有キャッシュ）はこの道具では検出できない。あれば実施条件に自分で書く",
    }
    violated = any(src_diff.values())
    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        c = report["実施条件"]
        print(f"## 実施条件\n- コマンド: {' '.join(cmd)}\n- 作業空間: {wd}\n- exit code: {code}{'（時間切れ）' if timed_out else ''}\n- Python {c['python']} / {c['os']}")
        print("\n## 成果物の場所の差分（空であること）\n" + tree_diff.render(src_diff))
        print("\n## 作業空間の差分（実行が書いたもの）\n" + tree_diff.render(ws_diff))
        print("\n## 出力（末尾）\n" + tail(out) + ("\n--- stderr ---\n" + tail(err) if err.strip() else ""))
        print("\n## 申告\n" + report["申告"])
        if violated:
            print("\n!! 成果物の場所が書き換わっている。復元せず、そのまま報告すること")
    return 1 if violated else 0


if __name__ == "__main__":
    sys.exit(main())
