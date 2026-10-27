#!/usr/bin/env python3
"""プロジェクトに .pair-agent/ を初期化する（テンプレートのコピー・Antigravity 用ディレクトリ・GEMINI.md・idle ポインタ）。既定は下見、--apply で書く。

使い方:
  python init_project.py --project . --apply
  python init_project.py --project . --home ~/.claude/pair-agent      # テンプレートの場所を変える

追加だけで既存ファイルは上書きしない。.pair-agent/ が既にあれば何もしない。空ディレクトリ（project-start-empty の管轄）では動かない（--force-empty で許す）。
終了コード: 0=実行/下見OK  1=対象外（既に初期化済み・空）  2=テンプレート無し（install の再実行を案内）
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import shutil
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

DEFAULT_HOME = Path.home() / ".claude" / "pair-agent"
DIRS = ("agreements", "sprints", "acceptance", "assurance", "skills", "current")
AGENT_DIRS = (".agents/skills", ".agents/agents", ".agents/workflows")


def toplevel(project: Path, override: str) -> str:
    if override:
        return override
    try:
        r = subprocess.run(["git", "-C", str(project), "rev-parse", "--show-toplevel"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
        return r.stdout.strip()
    except Exception:
        return str(project.resolve())


def has_existing_files(project: Path) -> bool:
    for c in project.iterdir():
        if c.name != ".git":
            return True
    return False


def plan(a) -> tuple[int, list[str], list[tuple[str, Path, str]]]:
    """(終了コード, メッセージ, 操作[(種別, パス, 補足)])。操作は mkdir / copy / write。"""
    project = Path(a.project).resolve()
    pa = project / ".pair-agent"
    if pa.exists():
        return 1, [".pair-agent/ が既にある。初期化しない"], []
    if not has_existing_files(project) and not a.force_empty:
        return 1, ["空ディレクトリ（project-start-empty の管轄）。方向が決まってから初期化する"], []
    tpl = Path(a.home) / "template"
    if not tpl.is_dir():
        return 2, ["テンプレートが見つからない。install.sh（または install.bat）を再実行してください: " + str(tpl)], []
    ops: list[tuple[str, Path, str]] = [("mkdir", pa, "")]
    for d in DIRS:
        ops.append(("mkdir", pa / d, ""))
    for src in sorted(tpl.rglob("*")):
        if src.is_file():
            ops.append(("copy", pa / src.relative_to(tpl), str(src)))
    for d in AGENT_DIRS:
        ops.append(("mkdir", project / d, ""))
    claude, gemini = project / "CLAUDE.md", project / "GEMINI.md"
    if claude.is_file() and not gemini.exists():
        ops.append(("copy", gemini, str(claude)))
    top = toplevel(project, a.toplevel)
    host = a.host or socket.gethostname()
    key = hashlib.sha1((host + top).encode("utf-8")).hexdigest()[:8]
    ts = a.now or datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    ptr = {"workcopy": {"host": host, "path": top, "key": key}, "sprint_id": None, "status": "idle",
           "journal": None, "updated_at": ts}
    ops.append(("write", pa / "current" / f"{key}-{Path(top).name}.json",
                json.dumps(ptr, ensure_ascii=False, indent=2) + "\n"))
    return 0, [], ops


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    p.add_argument("--project", default=".")
    p.add_argument("--home", default=str(DEFAULT_HOME), help="テンプレート置き場（<home>/template を使う）")
    p.add_argument("--host", default="", help="ホスト名（テスト用）")
    p.add_argument("--toplevel", default="", help="git toplevel の上書き（テスト用）")
    p.add_argument("--now", default="", help="タイムスタンプ固定（テスト用）")
    p.add_argument("--force-empty", action="store_true")
    p.add_argument("--apply", action="store_true")
    a = p.parse_args(argv)
    code, msgs, ops = plan(a)
    for m in msgs:
        print(m, file=sys.stderr if code == 2 else sys.stdout)
    if code:
        return code
    created = skipped = 0
    for kind, path, extra in ops:
        if kind == "mkdir":
            label = f"mkdir {path}"
            if a.apply:
                path.mkdir(parents=True, exist_ok=True)
        else:
            if path.exists():
                skipped += 1
                print(f"skip（既存）{path}")
                continue
            label = f"{kind} {path}"
            if a.apply:
                path.parent.mkdir(parents=True, exist_ok=True)
                if kind == "copy":
                    shutil.copyfile(extra, path)
                else:
                    path.write_text(extra, encoding="utf-8", newline="\n")
            created += 1
        print(("" if a.apply else "[下見] ") + label)
    print(f"\n{'実行' if a.apply else '下見'}: ファイル {created} 件作成/{skipped} 件スキップ")
    return 0


if __name__ == "__main__":
    sys.exit(main())
