"""境目: 改行だけの違い・取り消した取り込みの後の編集・常駐の監視（変更 1 回で点検 1 回、自分の書き込みでは動かない）。"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from conftest import write
from pamgr import changes, inbox, resident, settings, sweep
from test_sweep import commit_all, make_git_master, register_home


def test_line_endings_only_is_same(world: dict[str, Path]) -> None:
    m, home = world["master"], world["home"]
    make_git_master(m)
    (home / "rules/core.md").write_bytes((m / "home-claude/rules/core.md").read_bytes().replace(b"\n", b"\r\n"))
    register_home(world)
    pv = sweep.run(dry_run=True)
    assert not any("core.md" in a["detail"] for a in pv["actions"]), "改行だけの違いでは配らない"


def test_undone_adoption_is_not_deleted_by_later_edit(world: dict[str, Path]) -> None:
    m, home = world["master"], world["home"]
    make_git_master(m)
    write(home / "CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## 新しい宣言\n新しい規則。\n\n## 確認\n破壊的な操作の前は確認する。\n")
    register_home(world)
    sweep.run(llm_budget=0)
    commit_all(m, "publish")                      # 点検が push した後
    ev = next(e for e in changes.events() if "CLAUDE.md" in e["detail"])
    changes.undo(ev["id"])
    # 配布先で別の節を直す
    write(home / "CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。直した。\n\n## 新しい宣言\n新しい規則。\n\n## 確認\n破壊的な操作の前は確認する。\n")
    sweep.run(llm_budget=0)
    assert "## 新しい宣言" in (home / "CLAUDE.md").read_text(encoding="utf-8"), "取り消して残した節を、推測で消さない"
    assert any(i["kind"] == "J2" for i in inbox.items())


def test_resident_sweeps_once_per_change(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> None:
    make_git_master(world["master"])
    register_home(world)
    settings.put({"watch": True, "interval_min": 600, "llm_budget_sec": 0})
    monkeypatch.setattr(resident, "POLL_SEC", 0.1)
    calls: list[str] = []
    orig = resident.sweep_and_notify

    def counted(dry_run: bool = False, progress: object = None, reason: str = "") -> dict:
        calls.append(reason)
        return orig(dry_run, progress, reason)

    monkeypatch.setattr(resident, "sweep_and_notify", counted)

    def wait(n: int) -> None:
        t0 = time.time()
        while len(calls) < n and time.time() - t0 < 15:
            time.sleep(0.05)

    resident.start()
    try:
        wait(1)
        assert calls[:1] == ["定期"], "初めては、すぐ点検する"
        time.sleep(1.0)
        assert len(calls) == 1, "点検が自分で書いた分では動かない"
        write(world["home"] / "rules/core.md", "# core\n\n## 応答\n1 分以内に応答する。もう一度直した。\n")
        wait(2)
        assert calls[1:2] == ["ファイルの変更"]
        time.sleep(1.0)
        assert len(calls) == 2
    finally:
        resident.stop()
