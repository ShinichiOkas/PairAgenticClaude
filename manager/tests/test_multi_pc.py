"""複数の PC: マスターが分かれたときのマージ（節ごと → 無理なら J2）・判定の共有・ペア固有の層の同期（選べる）。
GitHub には触らない: 一時フォルダの bare リモートと clone だけ。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from conftest import write
from pamgr import changes, checks, conflicts, decide, gitsync, history, inbox, settings, sweep, targets
from test_resident_git import git, remote_master  # noqa: F401  (fixture)
from test_sweep import register_home

BASE = "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## 確認\n破壊的な操作の前は確認する。\n"


def edit_master(root: Path, text: str, msg: str, push: bool = False) -> None:
    write(root / "home-claude/CLAUDE.md", text)
    git(root, "commit", "-q", "-am", msg)
    if push:
        git(root, "push", "-q")
    history._versions.cache_clear()


def test_diverged_master_merges_by_section_and_pushes(remote_master: dict[str, Path]) -> None:
    m, other = remote_master["master"], remote_master["other"]
    sweep.run(llm_budget=0)
    git(other, "pull", "-q")
    edit_master(other, BASE.replace("破壊的な操作の前は確認する。", "破壊的な操作の前だけ確認する。"), "other: 確認", push=True)
    edit_master(m, (m / "home-claude/CLAUDE.md").read_text(encoding="utf-8").replace("判断は事後報告。", "判断は事後報告。速く回す。"), "me: 運転方針")
    res = sweep.run(llm_budget=0)
    assert res["git"]["pull"]["ok"] and res["git"]["pull"]["merged"]
    text = (m / "home-claude/CLAUDE.md").read_text(encoding="utf-8")
    assert "速く回す" in text and "前だけ確認" in text
    assert "速く回す" in git(remote_master["bare"], "show", "main:home-claude/CLAUDE.md"), "マージを push した"


def test_same_section_goes_to_j2_and_decide_theirs(remote_master: dict[str, Path]) -> None:
    m, other = remote_master["master"], remote_master["other"]
    sweep.run(llm_budget=0)
    git(other, "pull", "-q")
    edit_master(other, BASE.replace("破壊的な操作の前は確認する。", "GitHub の版。"), "other", push=True)
    edit_master(m, (m / "home-claude/CLAUDE.md").read_text(encoding="utf-8").replace("破壊的な操作の前は確認する。", "この PC の版。"), "me")
    sweep.run(llm_budget=0)
    items = [i for i in inbox.items() if i["key"].startswith("J2git|master|")]
    assert len(items) == 1 and "home-claude/CLAUDE.md" in items[0]["refs"]["files"]
    assert "<<<<<<<" not in (m / "home-claude/CLAUDE.md").read_text(encoding="utf-8"), "解けなければマージをやめて元に戻す"
    out = decide.decide(items[0]["id"], "theirs")
    assert "GitHub の版" in (m / "home-claude/CLAUDE.md").read_text(encoding="utf-8")
    assert "GitHub の版" in git(remote_master["bare"], "show", "main:home-claude/CLAUDE.md")
    with pytest.raises(ValueError):
        changes.undo(out["event"]["id"])


def test_global_verdicts_are_shared_through_master(world: dict[str, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rules = "# P\n\n## 運転方針\n依頼を受けたら着手する。\n\n## セッションの始め\n依頼が無ければ待つ。\n"
    write(world["home"] / "CLAUDE.md", rules)
    write(world["master"] / "home-claude/CLAUDE.md", rules)
    register_home(world)
    calls: list[str] = []

    def judge(a: dict, b: dict, model: str | None = None) -> tuple[checks.PairVerdict, str]:
        calls.append(a["anchor"])
        return checks.PairVerdict(relation="unrelated", reason="r"), "fake"

    monkeypatch.setattr(checks, "judge_pair", judge)
    sweep.run(llm_budget=30)
    n = len(calls)
    assert n > 0 and conflicts.shared_path().is_file()
    # 別の PC（データ置き場が別）: 共有ファイルの判定を使い回す
    monkeypatch.setenv("PAMGR_HOME", str(tmp_path / "pc2-home"))
    settings.put({"scan_roots": [str(tmp_path / "noscan")], "git_sync": False, "notify": False})
    register_home(world)
    sweep.run(llm_budget=30)
    assert len(calls) == n, "全体の規則どうしは判定し直さない"


@pytest.fixture
def pair(world: dict[str, Path], tmp_path: Path) -> dict[str, Path]:
    root = world["home"] / "pair-agent"
    git(root, "init", "-q", "-b", "master")
    git(root, "config", "user.email", "me@example.invalid"); git(root, "config", "user.name", "me")
    write(root / "skills/x.md", "# x\n\n## A\nいち。\n\n## B\nに。\n")
    git(root, "add", "-A"); git(root, "commit", "-q", "-m", "init")
    bare = tmp_path / "pair.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "master", str(bare)], check=True)
    register_home(world)
    return {"root": root, "bare": bare, "tmp": tmp_path}


def test_pair_sync_is_off_by_default(pair: dict[str, Path]) -> None:
    info, items = gitsync.pair_step()
    assert info == {"enabled": False} and items == []


def test_pair_sync_push_pull_merge_and_conflict(pair: dict[str, Path]) -> None:
    root, bare, tmp = pair["root"], pair["bare"], pair["tmp"]
    settings.put({"pair_sync_url": str(bare)})
    write(root / "corrections/new.md", "叱責の記録\n")            # まだ commit していない記録も持っていく
    res = sweep.run(llm_budget=0)
    assert res["git"]["pair"]["ok"] and res["git"]["pair"].get("first")
    assert "corrections/new.md" in git(bare, "ls-tree", "-r", "--name-only", "master")
    pc2 = tmp / "pc2-pair"
    subprocess.run(["git", "clone", "-q", str(bare), str(pc2)], check=True)
    git(pc2, "config", "user.email", "me@example.invalid"); git(pc2, "config", "user.name", "me")
    # 違う節 → 節ごとにマージ
    write(pc2 / "skills/x.md", "# x\n\n## A\nいち。\n\n## B\nに（別の PC）。\n"); git(pc2, "commit", "-q", "-am", "pc2"); git(pc2, "push", "-q")
    write(root / "skills/x.md", "# x\n\n## A\nいち（この PC）。\n\n## B\nに。\n")
    res = sweep.run(llm_budget=0)
    assert res["git"]["pair"]["ok"], res["git"]["pair"]
    t = (root / "skills/x.md").read_text(encoding="utf-8")
    assert "いち（この PC）" in t and "に（別の PC）" in t
    # 同じ節 → J2
    git(pc2, "pull", "-q")
    write(pc2 / "skills/x.md", (pc2 / "skills/x.md").read_text(encoding="utf-8").replace("いち（この PC）", "いち（別の PC）"))
    git(pc2, "commit", "-q", "-am", "pc2 again"); git(pc2, "push", "-q")
    write(root / "skills/x.md", t.replace("いち（この PC）", "いち（この PC・再び）"))
    sweep.run(llm_budget=0)
    assert [i["title"] for i in inbox.items() if i["key"].startswith("J2git|pair|")] == ["ペア固有の層の git の衝突"]


def test_pair_sync_refuses_unrelated_history(pair: dict[str, Path]) -> None:
    other = pair["tmp"] / "unrelated"
    git_dir = other / "w"
    subprocess.run(["git", "init", "-q", "-b", "master", str(git_dir)], check=True)
    git(git_dir, "config", "user.email", "x@example.invalid"); git(git_dir, "config", "user.name", "x")
    write(git_dir / "a.md", "別の履歴\n"); git(git_dir, "add", "-A"); git(git_dir, "commit", "-q", "-m", "x")
    settings.put({"pair_sync_url": str(git_dir)})
    info, _ = gitsync.pair_step()
    assert info["ok"] is False and "つながっていません" in info["error"]
    assert targets.list_targets()
