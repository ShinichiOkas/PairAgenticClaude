#!/usr/bin/env python3
"""既存プロジェクトの最初の見立て（.pair-agent の有無・言語/ビルド・README/テスト・git の状態と直近の履歴・大きいファイル）を簡潔に出す（読むだけ）。

使い方:
  python survey_project.py --project .
  python survey_project.py --project . --json

大量のファイルを読まない。ディレクトリを数え、ファイル名・拡張子・git の出力だけで要点を出す（中身は README の冒頭数行だけ）。
.pair-agent/ が無ければ「project-init を展開する」と案内する。空なら project-start-empty の管轄と案内する。
"""
from __future__ import annotations

import argparse
import collections
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".pytest_cache", "dist", "build", "target", ".idea", ".vs"}
BUILD_MARKERS = {
    "pyproject.toml": "Python", "setup.py": "Python", "requirements.txt": "Python",
    "package.json": "Node.js", "Cargo.toml": "Rust", "go.mod": "Go", "pom.xml": "Java (Maven)",
    "build.gradle": "Java/Kotlin (Gradle)", "Gemfile": "Ruby", "composer.json": "PHP",
    "CMakeLists.txt": "C/C++ (CMake)", "Makefile": "make", "Dockerfile": "Docker",
}
TEST_DIRS = ("tests", "test", "spec", "__tests__")
MAX_FILES = 20000


def git(project: Path, *args: str) -> str:
    try:
        r = subprocess.run(["git", "-C", str(project), *args], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=20)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def walk(project: Path):
    n = 0
    stack = [project]
    while stack:
        d = stack.pop()
        try:
            entries = sorted(d.iterdir())
        except OSError:
            continue
        for e in entries:
            if e.is_dir():
                if e.name not in SKIP_DIRS and not e.is_symlink():
                    stack.append(e)
            elif e.is_file():
                n += 1
                if n > MAX_FILES:
                    return
                yield e


def survey(project: Path, top_ext: int = 6, big: int = 5) -> dict:
    visible = [c.name for c in project.iterdir() if c.name != ".git"]
    ext = collections.Counter()
    sizes: list[tuple[int, str]] = []
    total = 0
    for f in walk(project):
        total += 1
        ext[f.suffix.lower() or "(なし)"] += 1
        try:
            sizes.append((f.stat().st_size, str(f.relative_to(project)).replace("\\", "/")))
        except OSError:
            pass
    sizes.sort(key=lambda x: (-x[0], x[1]))
    readme = next((c for c in sorted(project.iterdir()) if c.is_file() and c.stem.lower() == "readme"), None)
    readme_head = ""
    if readme:
        lines = readme.read_text(encoding="utf-8", errors="replace").splitlines()
        readme_head = " / ".join(l.strip() for l in lines if l.strip())[:200]
    tops = sorted(c.name for c in project.iterdir() if c.is_dir() and c.name not in SKIP_DIRS)
    status = git(project, "status", "--porcelain")
    is_git = bool(git(project, "rev-parse", "--is-inside-work-tree"))
    if not visible:
        verdict = "empty"
    elif (project / ".pair-agent").exists():
        verdict = "initialized"
    else:
        verdict = "needs-init"
    return {
        "verdict": verdict,
        "files": total, "truncated": total > MAX_FILES,
        "top_dirs": tops[:15],
        "extensions": ext.most_common(top_ext),
        "build": sorted({v for k, v in BUILD_MARKERS.items() if (project / k).exists()}),
        "readme": readme.name if readme else "",
        "readme_head": readme_head,
        "tests": [d for d in TEST_DIRS if (project / d).is_dir()],
        "agent_files": [n for n in ("CLAUDE.md", "GEMINI.md", "AGENTS.md") if (project / n).exists()],
        "git": {
            "is_repo": is_git, "branch": git(project, "rev-parse", "--abbrev-ref", "HEAD") if is_git else "",
            "dirty_files": len(status.splitlines()) if status else 0,
            "recent": git(project, "log", "-5", "--format=%h %s").splitlines() if is_git else [],
        },
        "biggest": [{"path": p, "bytes": s} for s, p in sizes[:big]],
    }


def render(s: dict) -> str:
    out = []
    guide = {"empty": "空 -> project-start-empty の管轄", "needs-init": ".pair-agent/ が無い -> project-init を展開してから接待を続ける",
             "initialized": ".pair-agent/ あり -> current/ のポインタを確認して状況を報告"}[s["verdict"]]
    out.append(f"判定: {guide}")
    out.append(f"ファイル {s['files']} 件" + ("（上限で打ち切り）" if s["truncated"] else "")
               + " / 拡張子: " + ", ".join(f"{e}:{n}" for e, n in s["extensions"]))
    out.append("トップ: " + (", ".join(s["top_dirs"]) or "(なし)"))
    out.append("ビルド/言語: " + (", ".join(s["build"]) or "判別できず"))
    out.append("README: " + (f"{s['readme']} — {s['readme_head']}" if s["readme"] else "なし"))
    out.append("テスト: " + (", ".join(s["tests"]) or "専用ディレクトリなし"))
    out.append("エージェント指示: " + (", ".join(s["agent_files"]) or "なし"))
    g = s["git"]
    if g["is_repo"]:
        out.append(f"git: {g['branch']} / 未コミット {g['dirty_files']} 件")
        out += [f"  {l}" for l in g["recent"]]
    else:
        out.append("git: リポジトリではない")
    out.append("大きいファイル: " + ", ".join(f"{b['path']}({b['bytes']:,}B)" for b in s["biggest"]))
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--project", default=".")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    project = Path(a.project).resolve()
    if not project.is_dir():
        print(f"ERROR: ディレクトリでない: {project}", file=sys.stderr)
        return 2
    s = survey(project)
    print(json.dumps(s, ensure_ascii=False, indent=2) if a.json else render(s))
    return 0


if __name__ == "__main__":
    sys.exit(main())
