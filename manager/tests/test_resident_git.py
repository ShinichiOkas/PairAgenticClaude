"""常駐（通知は新しい判断待ちに 1 回だけ・ログオン起動）と GitHub の段（ツールが書いたものだけ push・ほかのユーザーの変更は J4 で止める）。
GitHub には触らない: 一時フォルダの bare リモートと clone だけ。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import write
from pamgr import autostart, changes, decide, history, inbox, notify, resident, settings, sweep, targets
from test_sweep import register_home


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True, encoding="utf-8").stdout


def test_notify_once_per_new_item(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    shown: list[tuple[str, str, str]] = []
    monkeypatch.setattr(notify, "toast", lambda t, b, u: shown.append((t, b, u)) or {"ok": True})
    settings.put({"notify": True})
    inbox.upsert([{"kind": "J3", "key": "J3|x", "title": "x を管理に入れるか", "what": "", "options": []},
                  {"kind": "J1", "key": "J1|y", "title": "A × B", "what": "", "options": [], "initial_status": "info"}])
    resident.notify_new()
    resident.notify_new()
    assert len(shown) == 1 and "判断待ち 1 件" in shown[0][0] and shown[0][2].endswith("#inbox"), "急ぎでないもの（info）は通知しない"


def test_configure_autostart_and_resident(world: dict[str, Path]) -> None:
    st = resident.configure({"autostart": True, "interval_min": 45})
    assert st["autostart"] and autostart.launcher_path().is_file() and st["settings"]["interval_min"] == 45
    assert resident.configure({"autostart": False})["autostart"] is False
    st = resident.configure({"enabled": True})
    try:
        assert st["running"] is True
    finally:
        assert resident.configure({"enabled": False})["running"] is False


@pytest.fixture
def remote_master(world: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    bare, m = tmp_path / "remote.git", world["master"]
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
    git(m, "init", "-q", "-b", "main")
    git(m, "config", "user.email", "me@example.invalid"); git(m, "config", "user.name", "me")
    git(m, "add", "-A"); git(m, "commit", "-q", "-m", "v1")
    git(m, "remote", "add", "origin", str(bare)); git(m, "push", "-q", "-u", "origin", "main")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", "-q", str(bare), str(other)], check=True)
    git(other, "config", "user.email", "other@example.invalid"); git(other, "config", "user.name", "other")
    history._versions.cache_clear()
    settings.put({"git_sync": True})
    register_home(world)
    return {**world, "bare": bare, "other": other}


def test_publish_only_tool_written_files(remote_master: dict[str, Path]) -> None:
    m, home = remote_master["master"], remote_master["home"]
    write(home / "rules/core.md", "# core\n\n## 応答\n1 分以内に応答する。師匠の新しい追記。\n")       # 配布先だけが変わった → 取り込む
    write(m / "home-claude/skills/retro/SKILL.md", "---\nname: retro\n---\n師匠が編集中\n")          # マスターの編集中（ツールではない）
    res = sweep.run(llm_budget=0)
    assert res["git"]["publish"]["pushed"] is True
    pushed = git(remote_master["bare"], "show", "--name-only", "--format=", "main").split()
    assert "home-claude/rules/core.md" in pushed and "home-claude/skills/retro/SKILL.md" not in pushed
    assert "師匠が編集中" in (m / "home-claude/skills/retro/SKILL.md").read_text(encoding="utf-8")


def test_foreign_change_waits_for_j4_then_take(remote_master: dict[str, Path]) -> None:
    sweep.run(llm_budget=0)
    other, home = remote_master["other"], remote_master["home"]
    git(other, "pull", "-q")
    write(other / "home-claude/rules/core.md", "# core\n\n## 応答\n30 秒以内に応答する。\n")
    git(other, "commit", "-q", "-am", "other: 応答を 30 秒に"); git(other, "push", "-q")
    res = sweep.run(llm_budget=0)
    j4 = [i for i in inbox.items() if i["kind"] == "J4"]
    assert len(j4) == 1 and "home-claude/rules/core.md" in j4[0]["refs"]["files"]
    assert "30 秒" not in (home / "rules/core.md").read_text(encoding="utf-8"), "決めるまで配らない"
    assert any(h["why"].startswith("ほかのユーザー") for h in res["held"])
    decide.decide(j4[0]["id"], "take")
    sweep.run(llm_budget=0)
    assert "30 秒" in (home / "rules/core.md").read_text(encoding="utf-8")


def test_foreign_change_reject_restores_master(remote_master: dict[str, Path]) -> None:
    sweep.run(llm_budget=0)
    other, m = remote_master["other"], remote_master["master"]
    git(other, "pull", "-q")
    before = (m / "home-claude/rules/core.md").read_bytes()
    write(other / "home-claude/rules/core.md", "# core\n\n## 応答\n30 秒以内に応答する。\n")
    git(other, "commit", "-q", "-am", "other"); git(other, "push", "-q")
    sweep.run(llm_budget=0)
    j4 = [i for i in inbox.items() if i["kind"] == "J4"][0]
    decide.decide(j4["id"], "reject")
    assert (m / "home-claude/rules/core.md").read_bytes() == before
    sweep.run(llm_budget=0)
    assert git(remote_master["bare"], "show", "main:home-claude/rules/core.md").encode("utf-8").replace(b"\r\n", b"\n") == before.replace(b"\r\n", b"\n")
    assert targets.list_targets() and changes.events()
