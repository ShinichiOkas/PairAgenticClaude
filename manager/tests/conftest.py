"""テストは実データ（~/.claude・~/.gemini・兄弟リポジトリ・このリポジトリのマスター）に書かない。
PAMGR_HOME（データ置き場）・PAMGR_USER_HOME（配布先のホーム）・PAMGR_MASTER（マスター）を一時フォルダに向ける。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def write(p: Path, text: str) -> Path:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PAMGR_HOME", str(tmp_path / "pamgr-home"))
    monkeypatch.setenv("PAMGR_USER_HOME", str(tmp_path / "userhome"))
    monkeypatch.setenv("PAMGR_MASTER", str(tmp_path / "master"))
    (tmp_path / "userhome").mkdir()
    (tmp_path / "master").mkdir()
    # テストは LLM を呼ばない（使うテストは自分で差し替える）
    from pamgr import llm

    def no_llm(*_a: object, **_k: object) -> None:
        raise llm.LLMNotConfigured("テストでは LLM を使わない")

    monkeypatch.setattr(llm, "chat_structured", no_llm)
    monkeypatch.setattr(llm, "chat_text", no_llm)
    # 点検の探索は、テストが根を与えたときだけ（既定では空のフォルダを見る）
    (tmp_path / "noscan").mkdir()
    from pamgr import settings
    settings.put({"scan_roots": [str(tmp_path / "noscan")]})
    return tmp_path


@pytest.fixture
def world(isolated: Path) -> dict[str, Path]:
    """偽のマスター・ホーム・プロジェクト 2 つ。"""
    m = isolated / "master"
    write(m / "home-claude/CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## 確認\n破壊的な操作の前は確認する。\n")
    write(m / "home-claude/GEMINI.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n")
    write(m / "home-claude/rules/core.md", "# core\n\n## 応答\n1 分以内に応答する。\n")
    write(m / "home-claude/skills/retro/SKILL.md", "---\nname: retro\ndescription: 振り返り\n---\n振り返りはスキル確認だけ。\n")
    write(m / "home-claude/agents/deliberation.md", "協議エンジン\n")
    write(m / "project-template/.pair-agent/skills/.gitkeep", "")
    home = isolated / "userhome" / ".claude"
    write(home / "CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## 確認\n破壊的な操作の前は確認する。\n")
    write(home / "rules/core.md", "# core\n\n## 応答\n1 分以内に応答する。師匠の新しい追記。\n")
    write(home / "pair-agent/skills/ui-first.md", "---\nname: ui-first\ndescription: UI を先に\n---\nUI を先に作る。中身は未実装と返す。\n")
    dev = isolated / "dev"
    write(dev / "Alpha/CLAUDE.md", "# Alpha\n\n## 確認\n破壊的な操作の前は確認する。\n")
    write(dev / "Alpha/.pair-agent/skills/alpha-db.md",
          "---\nname: alpha-db\ndescription: Alpha の DB\n---\nAlpha では ALPHA_WORK_DIR の下に置く。C:\\Users\\someone\\alpha\\db を使う。\n")
    write(dev / "Beta/.claude/settings.json", "{}")
    write(dev / "Beta/AGENTS.md", "# Beta\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n")
    (dev / "NotAProject/src").mkdir(parents=True)
    return {"master": m, "home": home, "dev": dev}


@pytest.fixture
def client() -> TestClient:
    from pamgr.app import create_app

    return TestClient(create_app())
