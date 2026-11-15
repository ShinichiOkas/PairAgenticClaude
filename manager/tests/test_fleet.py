"""fleet: 一時フォルダの bare リモート + 2 つの clone だけで git 同期を確かめる（実リポジトリ・GitHub には触らない）。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from pamgr import fleet
from tests.conftest import write


def git(cwd: Path, *args: str) -> str:
    p = subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, encoding="utf-8", check=True)
    return p.stdout.strip()


def setup_repo(path: Path, email: str, name: str) -> None:
    git(path, "config", "user.email", email)
    git(path, "config", "user.name", name)
    git(path, "config", "commit.gpgsign", "false")


@pytest.fixture
def trio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """bare リモート・自分の clone（PAMGR_MASTER）・別の PC の clone。初期コミット済み。"""
    remote = tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    mine = tmp_path / "mine"
    subprocess.run(["git", "clone", str(remote), str(mine)], check=True, capture_output=True)
    setup_repo(mine, "me@example.com", "Me")
    git(mine, "checkout", "-B", "main")
    write(mine / "home-claude/CLAUDE.md", "# base\n")
    write(mine / "README.md", "readme\n")
    git(mine, "add", "-A")
    git(mine, "commit", "-m", "init")
    git(mine, "push", "-u", "origin", "main")
    other = tmp_path / "other"
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    setup_repo(other, "other@example.com", "Other PC")
    monkeypatch.setenv("PAMGR_MASTER", str(mine))
    return {"remote": remote, "mine": mine, "other": other}


def other_commit(other: Path, rel: str, text: str, msg: str) -> None:
    write(other / rel, text)
    git(other, "add", "-A")
    git(other, "commit", "-m", msg)


def test_status_clean(trio):
    s = fleet.status()
    assert s["ok"] is True
    assert s["branch"] == "main"
    assert s["head"] == git(trio["mine"], "rev-parse", "HEAD")
    assert s["remote"] and "remote.git" in s["remote"]
    assert (s["ahead"], s["behind"]) == (0, 0)
    assert s["dirty"] == []


def test_status_ahead_dirty(trio):
    mine = trio["mine"]
    write(mine / "home-claude/rules/new.md", "x\n")
    write(mine / "situations/s.json", "{}\n")
    write(mine / "README.md", "changed outside tool paths\n")
    s = fleet.status()
    assert s["dirty"] == ["home-claude/rules/new.md", "situations/s.json"]  # TOOL_PATHS の外は出さない
    write(mine / "home-claude/CLAUDE.md", "# base\nmore\n")
    git(mine, "add", "home-claude/CLAUDE.md")
    git(mine, "commit", "-m", "local")
    assert fleet.status()["ahead"] == 1


def test_status_behind_after_fetch(trio):
    other_commit(trio["other"], "home-claude/rules/r.md", "r\n", "other rule")
    git(trio["other"], "push")
    assert fleet.status()["behind"] == 0  # fetch していないので見えない
    s = fleet.status(fetch=True)
    assert (s["ahead"], s["behind"]) == (0, 1)


def test_pull_up_to_date(trio):
    r = fleet.pull()
    assert r["ok"] is True and r["changed"] == [] and r["foreign"] == []
    assert r["old_head"] == r["new_head"]


def test_pull_fast_forward_foreign(trio):
    other = trio["other"]
    other_commit(other, "home-claude/rules/r.md", "r\n", "他 PC のルール")
    other_commit(other, "docs/outside.md", "o\n", "tool 外の変更")
    git(other, "push")
    old = git(trio["mine"], "rev-parse", "HEAD")
    r = fleet.pull()
    assert r["ok"] is True and r["diverged"] is False
    assert r["old_head"] == old and r["new_head"] == git(other, "rev-parse", "HEAD")
    assert sorted(r["changed"]) == ["docs/outside.md", "home-claude/rules/r.md"]
    assert [f["subject"] for f in r["foreign"]] == ["他 PC のルール", "tool 外の変更"]
    assert r["foreign"][0]["email"] == "other@example.com"
    assert r["foreign"][0]["author"] == "Other PC"
    assert r["foreign"][0]["files"] == ["home-claude/rules/r.md"]
    assert r["foreign"][1]["files"] == []  # TOOL_PATHS の外は載せない
    assert (trio["mine"] / "home-claude/rules/r.md").read_text(encoding="utf-8") == "r\n"


def test_pull_own_commit_not_foreign(trio):
    other = trio["other"]
    git(other, "config", "user.email", "me@example.com")
    other_commit(other, "home-claude/rules/mine.md", "m\n", "自分の別 PC のコミット")
    git(other, "push")
    r = fleet.pull()
    assert r["ok"] is True and r["changed"] == ["home-claude/rules/mine.md"]
    assert r["foreign"] == []


def test_pull_diverged(trio):
    mine = trio["mine"]
    other_commit(trio["other"], "home-claude/rules/r.md", "r\n", "other")
    git(trio["other"], "push")
    write(mine / "home-claude/rules/l.md", "l\n")
    git(mine, "add", "-A")
    git(mine, "commit", "-m", "local")
    head = git(mine, "rev-parse", "HEAD")
    r = fleet.pull()
    assert r["ok"] is False and r["diverged"] is True and r["error"]
    assert git(mine, "rev-parse", "HEAD") == head  # 何も壊さない


def test_pull_no_upstream(tmp_path, monkeypatch):
    repo = tmp_path / "solo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    setup_repo(repo, "me@example.com", "Me")
    write(repo / "home-claude/a.md", "a\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-m", "a")
    monkeypatch.setenv("PAMGR_MASTER", str(repo))
    r = fleet.pull()
    assert r["ok"] is False and "upstream" in r["error"]
    assert fleet.status()["remote"] is None
    # upstream が無くても publish は commit だけして ok
    write(repo / "situations/s.json", "{}\n")
    p = fleet.publish("add s")
    assert p["ok"] is True and p["commit"] and p["pushed"] is False and p["files"] == ["situations/s.json"]


def test_publish_only_tool_paths_and_pushes(trio):
    mine = trio["mine"]
    write(mine / "home-claude/rules/new.md", "n\n")
    write(mine / "situations/s.json", "{}\n")
    write(mine / "README.md", "outside\n")  # TOOL_PATHS の外（未 stage）
    write(mine / "docs/staged.md", "staged\n")  # TOOL_PATHS の外（stage 済み）
    git(mine, "add", "docs/staged.md")
    r = fleet.publish("feat: 規則を追加")
    assert r["ok"] is True and r["pushed"] is True
    assert sorted(r["files"]) == ["home-claude/rules/new.md", "situations/s.json"]
    assert r["commit"] == git(mine, "rev-parse", "HEAD")
    assert git(trio["remote"], "rev-parse", "main") == r["commit"]
    assert git(mine, "log", "-1", "--format=%s") == "feat: 規則を追加"
    committed = git(mine, "show", "--name-only", "--format=", "HEAD").splitlines()
    assert sorted(committed) == ["home-claude/rules/new.md", "situations/s.json"]
    # 外のファイルは未コミットのまま・stage 済みも stage のまま
    assert "README.md" in git(mine, "status", "--porcelain")
    assert git(mine, "diff", "--cached", "--name-only") == "docs/staged.md"


def test_publish_nothing_to_commit(trio):
    write(trio["mine"] / "README.md", "outside only\n")
    head = git(trio["mine"], "rev-parse", "HEAD")
    r = fleet.publish("noop")
    assert r == {"ok": True, "commit": None, "pushed": False, "files": []}
    assert git(trio["mine"], "rev-parse", "HEAD") == head


def test_publish_missing_tool_paths(trio):
    # situations/ が無くても失敗しない
    assert not (trio["mine"] / "situations").exists()
    write(trio["mine"] / "home-claude/x.md", "x\n")
    r = fleet.publish("x")
    assert r["ok"] is True and r["files"] == ["home-claude/x.md"]


def test_publish_push_rejected_reports_not_forces(trio):
    other_commit(trio["other"], "home-claude/rules/r.md", "r\n", "other")
    git(trio["other"], "push")
    write(trio["mine"] / "home-claude/rules/l.md", "l\n")
    r = fleet.publish("local")
    assert r["ok"] is False and r["pushed"] is False and r["commit"] and r["error"]
    assert git(trio["remote"], "rev-parse", "main") == git(trio["other"], "rev-parse", "HEAD")  # 上書きしていない


def test_not_a_git_repo(isolated):
    # conftest の PAMGR_MASTER は空の一時フォルダ（git ではない）
    s = fleet.status()
    assert s["ok"] is False and s["error"]
    assert fleet.pull()["ok"] is False
    p = fleet.publish("m")
    assert p["ok"] is False and p["commit"] is None
