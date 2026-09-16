#!/usr/bin/env python3
"""
deny_read.py -- PreToolUse フックによるサブエージェントの読み取り遮断機構。
AgentRoleDesign の受入検査隔離規約および各成果物モデルの `blocks` を実行時に強制する。

Mnemo プロジェクトでの実走・検証済み（2026-09-16）:
- frontmatter の hooks ではなく、プロジェクトの settings.json (PreToolUse) または Antigravity hooks から起動。
- stdin からフックの JSON ペイロードを受け取り、`agent_type` を参照して `deny-map.json` から glob を引く。
- 親セッション（主エージェント）には `agent_type` が無いため、即座に exit 0 で通過（親へのオーバーヘッドなし）。
- サブエージェントが遮断対象パスを Read / Grep / Glob / Bash しようとした場合は exit 2 でブロック。
- Windows の cp932 問題に対処: stdin.buffer から直接 UTF-8 デコードを行い、日本語パスでの例外・fail-open を防止。
- Python 実行により、PowerShell (1.1秒/回) に対して 0.3秒/回の低遅延を実現。

セルフテスト:
    python tools/deny_read.py --selftest
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path


def norm(p: str) -> str:
    return (p or "").replace("\\", "/").rstrip("/").lower()


def glob_to_regex(glob: str) -> str:
    g = norm(glob)
    r = re.escape(g)
    r = r.replace(re.escape("**/"), "(?:.*/)?").replace(re.escape("**"), ".*").replace(re.escape("*"), "[^/]*")
    return "^" + r + "(?:/.*)?$" if "/" in g else "(?:^|/)" + r + "$"


def deny_root(glob: str) -> str:
    g = norm(glob)
    i = g.find("*")
    return (g[:i] if i >= 0 else g).rstrip("/")


def trace(msg: str) -> None:
    try:
        log_dir = Path(os.environ.get("TEMP") or os.environ.get("TMP") or ".").resolve()
        path = log_dir / "deny-read.log"
        with open(path, "a", encoding="utf-8", errors="replace") as fh:
            fh.write(time.strftime("%Y-%m-%d %H:%M:%S") + " " + msg + "\n")
    except Exception:
        pass


def decide(payload: dict, deny: str, root: str) -> tuple[str | None, str]:
    """Return (hit_glob or None, target). Pure function."""
    root_n = norm(os.path.abspath(root))
    globs = [g.strip() for g in deny.split(",") if g.strip()]

    def to_rel(p: str) -> str:
        if not p:
            return ""
        full = p if os.path.isabs(p) else os.path.join(root, p)
        n = norm(os.path.abspath(full))
        if n.startswith(root_n + "/"):
            return n[len(root_n) + 1:]
        return "" if n == root_n else n

    def blocked(rel: str, is_search_root: bool) -> str | None:
        for g in globs:
            if re.search(glob_to_regex(g), rel):
                return g
            if is_search_root:
                dr = deny_root(g)
                if dr and (rel == "" or rel == dr or rel.startswith(dr + "/") or dr.startswith(rel + "/")):
                    return g
        return None

    tool = str(payload.get("tool_name") or "")
    ti = payload.get("tool_input") or {}
    if tool == "Read":
        target = to_rel(str(ti.get("file_path") or ""))
        return blocked(target, False), target
    if tool in ("Grep", "Glob"):
        target = to_rel(str(ti.get("path") or root))
        return blocked(target, True), target
    if tool == "Bash":
        cmd = str(ti.get("command") or "")
        low = cmd.lower()
        for g in globs:
            dr = deny_root(g)
            if dr and (dr + "/" in low or dr.replace("/", "\\") + "\\" in low):
                return g, cmd
        return None, cmd
    return None, ""


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    deny = argv[argv.index("--deny") + 1] if "--deny" in argv else ""
    mapf = argv[argv.index("--map") + 1] if "--map" in argv else ""

    # bytes -> UTF-8 explicitly: Windows の cp932 デフォルトでの日本語文字化け・例外回避
    try:
        raw = sys.stdin.buffer.read().decode("utf-8", errors="replace")
    except Exception:
        raw = ""

    if not raw.strip():
        return 0

    try:
        payload = json.loads(raw)
    except Exception:
        trace("json parse failed")
        return 0

    agent = ""
    for k in ("agent_type", "agentType", "subagent_type"):
        if payload.get(k):
            agent = str(payload[k])
            break

    if mapf:
        if not agent:
            return 0  # 親セッション（主エージェント）は無条件パス
        try:
            with open(mapf, encoding="utf-8") as fh:
                m = json.load(fh)
        except Exception:
            trace("map load failed: " + mapf)
            return 0
        deny = str(m.get(agent) or "")

    if not deny:
        return 0

    root = os.environ.get("CLAUDE_PROJECT_DIR") or str(payload.get("cwd") or os.getcwd())
    hit, target = decide(payload, deny, root)
    trace(f"agent={agent} tool={payload.get('tool_name')} target={target} hit={hit}")

    if hit:
        sys.stderr.write(
            f"BLOCKED by role definition: '{target}' is under the read block '{hit}'. "
            f"This artifact is not in your deps. Do not work around it; report it as out of scope if needed.\n"
        )
        return 2

    return 0


def selftest() -> int:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    cases = [
        ("Read src", "src/**,tests/**", {"tool_name": "Read", "tool_input": {"file_path": os.path.join(root, "src", "main.py")}}, True),
        ("Read doc", "src/**,tests/**", {"tool_name": "Read", "tool_input": {"file_path": "doc/SPEC.md"}}, False),
        ("Grep root", "src/**,tests/**", {"tool_name": "Grep", "tool_input": {"pattern": "x"}}, True),
        ("Grep doc", "src/**,tests/**", {"tool_name": "Grep", "tool_input": {"pattern": "x", "path": "doc"}}, False),
        ("Glob tests", "src/**,tests/**", {"tool_name": "Glob", "tool_input": {"pattern": "*.py", "path": "tests"}}, True),
        ("Bash cat src", "src/**,tests/**", {"tool_name": "Bash", "tool_input": {"command": "cat src/main.py"}}, True),
        ("Bash git status", "src/**,tests/**", {"tool_name": "Bash", "tool_input": {"command": "git status"}}, False),
        ("Read acceptance", ".pair-agent/acceptance/**", {"tool_name": "Read", "tool_input": {"file_path": ".pair-agent/acceptance/test.md"}}, True),
        ("Read assurance", ".pair-agent/acceptance/**", {"tool_name": "Read", "tool_input": {"file_path": ".pair-agent/assurance/assure.md"}}, False),
        ("Japanese path blocked", "受入検査/**", {"tool_name": "Read", "tool_input": {"file_path": "受入検査/仕様.md"}}, True),
    ]
    bad = 0
    for name, deny, payload, expect in cases:
        hit, _ = decide(payload, deny, root)
        ok = bool(hit) == expect
        bad += 0 if ok else 1
        print(("OK  " if ok else "NG  ") + name)
    print("SELFTEST", "ALL OK" if not bad else str(bad) + " FAILED")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
