"""配布の対応表: マスター（このリポジトリ）のどのファイルが、どの種類の配布先のどこへ行くか。

根の install.bat（全体）と emit_agents.py（プロジェクト）の配り方を写したもの。
scope:
  global   全体（~/.claude・~/.gemini/config の規範・スキル・エージェント・道具・雛形）
  user     ユーザー固有（ペア固有スキル: external/pair-agent-skills → ~/.claude/pair-agent/skills）
  project  プロジェクト固有（雛形・エージェント定義・ワークフロー）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .paths import master_root

HOMES = ("claude_home", "gemini_home")
INSTALL_TOOLS = (
    "skill-survey.py", "survey-dev-prefs.py", "derive_roles.py", "simulate_mk.py", "check_skills.py",
    "check_report.py", "emit_claude.py", "emit_agents.py", "run_workflow.py", "deny_read.py",
    "measure_agent_usage.py", "design_graph.py",
)


@dataclass(frozen=True)
class Entry:
    id: str
    scope: str
    kinds: tuple[str, ...]
    src: str                      # マスターの中の相対パス（ファイルまたはフォルダ）
    dest: str                     # 配布先の中の相対パス（ファイルまたはフォルダ）
    globs: tuple[str, ...] = ()   # src がフォルダのときの対象
    files: tuple[str, ...] = ()   # src がフォルダで、名指しのファイルだけ配るとき
    track_extra: bool = False     # 配布先にだけあるファイルも数えるか
    requires_dest_dir: bool = False  # 配布先にそのフォルダがあるときだけ対象にする（採用していないプロジェクトを騒がせない）
    label: str = field(default="")


ENTRIES: tuple[Entry, ...] = (
    Entry("claude-md", "global", ("claude_home",), "home-claude/CLAUDE.md", "CLAUDE.md", label="主エージェントの規範（Claude）"),
    Entry("gemini-md", "global", ("gemini_home",), "home-claude/GEMINI.md", "GEMINI.md", label="主エージェントの規範（Gemini）"),
    Entry("rules", "global", HOMES, "home-claude/rules", "rules", ("*.md",), label="ルール"),
    Entry("skills", "global", HOMES, "home-claude/skills", "skills", ("*/SKILL.md", "*/scripts/*.py"), label="スキル"),
    Entry("agents", "global", HOMES, "home-claude/agents", "agents", ("*.md",), label="コアのサブエージェント"),
    Entry("tools", "global", HOMES, "tools", "pair-agent/tools", files=INSTALL_TOOLS, label="道具"),
    Entry("template", "global", HOMES, "home-claude/pair-agent/template", "pair-agent/template", ("**/*",), label="プロジェクトの雛形"),
    Entry("pair-skills", "user", HOMES, "external/pair-agent-skills", "pair-agent/skills", ("*.md",), track_extra=True, label="ペア固有スキル"),
    Entry("project-template", "project", ("project",), "project-template", "", ("**/*",), label="プロジェクトの雛形"),
    Entry("claude-agents", "project", ("project",), ".claude/agents", ".claude/agents", ("*.md",), requires_dest_dir=True, label="役割エージェント（Claude）"),
    Entry("claude-workflows", "project", ("project",), ".claude/workflows", ".claude/workflows", ("*",), requires_dest_dir=True, label="ワークフロー（Claude）"),
    Entry("agents-agents", "project", ("project",), ".agents/agents", ".agents/agents", ("*.md",), requires_dest_dir=True, label="役割エージェント（Antigravity）"),
    Entry("agents-workflows", "project", ("project",), ".agents/workflows", ".agents/workflows", ("*",), requires_dest_dir=True, label="ワークフロー（Antigravity）"),
)


def _rel(p: Path, base: Path) -> str:
    return p.relative_to(base).as_posix()


def expand(entry: Entry, master: Path | None = None) -> Iterator[tuple[Path, str]]:
    """(マスターのファイル, 配布先の中の相対パス) を列挙する。"""
    master = master or master_root()
    src = master / entry.src
    if src.is_file():
        yield src, entry.dest
        return
    if not src.is_dir():
        return
    seen: set[Path] = set()
    if entry.files:
        cands = [src / f for f in entry.files]
    else:
        cands = [p for g in entry.globs for p in src.glob(g)]
    for p in sorted(cands):
        if p in seen or not p.is_file() or "__pycache__" in p.parts:
            continue
        seen.add(p)
        rel = _rel(p, src)
        yield p, f"{entry.dest}/{rel}" if entry.dest else rel


def extra_in_target(entry: Entry, target_root: Path, known: set[str]) -> Iterator[str]:
    """配布先にだけあるファイル（track_extra のエントリのみ）。"""
    if not entry.track_extra:
        return
    d = target_root / entry.dest
    if not d.is_dir():
        return
    for g in entry.globs or ("*",):
        for p in sorted(d.glob(g)):
            if p.is_file():
                rel = _rel(p, target_root)
                if rel not in known:
                    yield rel


def entries_for(kind: str, scope: str | None = None) -> list[Entry]:
    return [e for e in ENTRIES if kind in e.kinds and (scope is None or e.scope == scope)]
