"""点検（ホーム）: 予行は書かない・配る・取り込む・節ごとのマージ・J2・取り消しは繰り返さない。すべて一時フォルダの中。"""

from __future__ import annotations

import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from conftest import write
from pamgr import changes, decide, history, inbox, sections, sweep, targets


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def commit_all(root: Path, msg: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", msg)
    history._versions.cache_clear()


def make_git_master(m: Path) -> None:
    git(m, "init", "-q")
    git(m, "config", "user.email", "t@example.invalid")
    git(m, "config", "user.name", "t")
    commit_all(m, "v1")


def snapshot(*roots: Path) -> dict[str, bytes]:
    return {str(p): p.read_bytes() for r in roots for p in sorted(r.rglob("*")) if p.is_file() and ".git" not in p.parts}


def register_home(world: dict[str, Path]) -> str:
    targets.register([{"kind": "claude_home", "path": str(world["home"]), "name": "~/.claude"}])
    return targets.list_targets()[0]["id"]


def test_sections_round_trip_and_replace() -> None:
    text = "# T\r\n\r\n## A\r\na\r\n## B\r\nb\r\n\r\n## C\r\nc\r\n"
    assert sections.join(sections.parse(text)) == text
    out = sections.replace(text, "B", sections.parse(text)[2].norm, "## B\nb2\n")
    assert out == "# T\r\n\r\n## A\r\na\r\n## B\r\nb2\r\n\r\n## C\r\nc\r\n"
    assert "## B" not in sections.replace(text, "B", None, "")


def test_dry_run_writes_nothing_then_sweep_merges_and_is_idempotent(world: dict[str, Path]) -> None:
    m, home = world["master"], world["home"]
    make_git_master(m)
    # マスターで「確認」の節を直す（配布先は古いまま）。配布先では新しい節を足す
    write(m / "home-claude/CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## 確認\n破壊的・不可逆の操作の前だけ確認する。\n")
    commit_all(m, "v2")
    write(home / "CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## UI ファースト\nUI を先に作る。\n\n## 確認\n破壊的な操作の前は確認する。\n")
    register_home(world)
    before = snapshot(m, home)

    pv = sweep.run(dry_run=True)
    assert snapshot(m, home) == before, "予行は何も書かない"
    kinds = {(a["kind"], a["detail"].split(" ")[0]) for a in pv["actions"]}
    assert ("merge", "~/.claude/CLAUDE.md") in kinds
    assert changes.events() == []

    res = sweep.run()
    assert res["skipped"] == []
    mc = (m / "home-claude/CLAUDE.md").read_text(encoding="utf-8")
    hc = (home / "CLAUDE.md").read_text(encoding="utf-8")
    assert mc == hc
    assert "## UI ファースト" in mc and "破壊的・不可逆の操作の前だけ" in mc
    assert mc.index("## 運転方針") < mc.index("## UI ファースト") < mc.index("## 確認")
    # マスターの GEMINI.md は CLAUDE.md と同じ中身を保つ（元は違うので触らない）
    ev = changes.events()
    assert any(e["kind"] == "merge" for e in ev)
    # rules/core.md は配布先だけが変わった（マスターは一度も変えていない）→ マスターへ取り込む
    assert "師匠の新しい追記" in (m / "home-claude/rules/core.md").read_text(encoding="utf-8")

    n = len(changes.events())
    after = snapshot(m, home)
    again = sweep.run()
    assert again["actions"] == [] and len(changes.events()) == n and snapshot(m, home) == after


def test_undo_restores_files_and_ledger_and_is_not_repeated(world: dict[str, Path]) -> None:
    m, home = world["master"], world["home"]
    make_git_master(m)
    write(home / "CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## 新しい宣言\n新しい規則。\n\n## 確認\n破壊的な操作の前は確認する。\n")
    register_home(world)
    before = snapshot(m, home)
    sweep.run()
    merges = [e for e in changes.events() if e["kind"] in ("merge", "adopt") and "CLAUDE.md" in e["detail"]]
    assert merges
    for e in reversed(changes.events()):
        if e["kind"] != "undo":
            changes.undo(e["id"])
    assert snapshot(m, home) == before
    n = len(changes.events())
    sweep.run()
    sweep.run()
    assert len(changes.events()) == n, "取り消した動作を点検が繰り返さない"
    assert snapshot(m, home) == before


def test_conflict_goes_to_j2_and_decide_then_undo_reopens(world: dict[str, Path]) -> None:
    m, home = world["master"], world["home"]
    make_git_master(m)
    write(m / "home-claude/CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## 確認\nマスターの書き換え。\n")
    commit_all(m, "v2")
    write(home / "CLAUDE.md", "# Pair Agent\n\n## 運転方針\n推奨で即着手する。判断は事後報告。\n\n## 確認\n配布先の書き換え。\n")
    register_home(world)
    sweep.run()
    items = [i for i in inbox.items() if i["kind"] == "J2"]
    assert len(items) == 1 and "確認" in items[0]["what"]
    assert "配布先の書き換え" in (home / "CLAUDE.md").read_text(encoding="utf-8")   # 判断の前は書かない

    out = decide.decide(items[0]["id"], "master")
    assert out["status"] == "decided"
    assert (home / "CLAUDE.md").read_bytes() == (m / "home-claude/CLAUDE.md").read_bytes()
    assert inbox.items() == []
    res = changes.undo(out["event"]["id"])
    decide.after_undo(res["refs"])
    assert "配布先の書き換え" in (home / "CLAUDE.md").read_text(encoding="utf-8")
    assert [i["status"] for i in inbox.items()] == ["open"]


def test_api_sweep_inbox_activity(world: dict[str, Path], client: TestClient) -> None:
    make_git_master(world["master"])
    register_home(world)
    r = client.post("/api/sweep", json={"dry_run": True}).json()
    assert r["implemented"] and r["job_id"]
    import time
    for _ in range(100):
        j = client.get(f"/api/jobs/{r['job_id']}").json()
        if j["state"] != "running":
            break
        time.sleep(0.05)
    assert j["state"] == "done", j
    assert client.get("/api/sweep").json()["preview"]["dry_run"] is True
    assert client.get("/api/inbox").json()["items"] == []
    assert client.get("/api/activity").json()["events"] == []
    assert client.post("/api/activity/nope/undo").status_code == 400
    assert client.post("/api/inbox/nope/decide", json={"option": "master"}).status_code == 400
