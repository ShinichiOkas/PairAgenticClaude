"""管理下（UC3）: ホームと .pair-agent/ を持つプロジェクトは自動で入れる。持たないものは J3。外したものは二度と聞かない。取り消せる。"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from pamgr import changes, decide, inbox, managed, settings, sweep, targets


def names() -> set[str]:
    return {t["name"] for t in targets.list_targets()}


def test_dry_run_registers_nothing_and_previews(world: dict[str, Path]) -> None:
    settings.put({"scan_roots": [str(world["dev"])]})
    pv = sweep.run(dry_run=True)
    assert targets.list_targets() == []
    assert {c["name"] for c in pv["managed"]["register"]} == {"Alpha", "~/.claude"}
    assert [i["title"] for i in pv["inbox"] if i["kind"] == "J3"] == ["Beta を管理に入れるか"]
    assert inbox.items() == []


def test_sweep_includes_and_asks_then_decisions_and_undo(world: dict[str, Path]) -> None:
    settings.put({"scan_roots": [str(world["dev"])]})
    sweep.run(llm_budget=0)
    assert names() == {"Alpha", "~/.claude"}
    assert sum(1 for e in changes.events() if e["kind"] == "manage") == 2
    j3 = [i for i in inbox.items() if i["kind"] == "J3"]
    assert len(j3) == 1 and "Beta" in j3[0]["title"]

    out = decide.decide(j3[0]["id"], "include")
    assert "Beta" in names()
    res = changes.undo(out["event"]["id"])
    managed.after_undo(res["refs"]); decide.after_undo(res["refs"])
    assert "Beta" not in names() and [i["status"] for i in inbox.items() if i["kind"] == "J3"] == ["open"]

    decide.decide(j3[0]["id"], "exclude")
    sweep.run(llm_budget=0)
    assert [i for i in inbox.items() if i["kind"] == "J3"] == [], "外したものは二度と聞かない"

    auto = next(e for e in changes.events() if e["kind"] == "manage" and "Alpha" in e["detail"])
    res = changes.undo(auto["id"])
    managed.after_undo(res["refs"])
    assert "Alpha" not in names()
    sweep.run(llm_budget=0)
    assert "Alpha" not in names(), "自動で入れたものを取り消したら、二度と自動で入れない"


def test_managed_api(world: dict[str, Path], client: TestClient) -> None:
    settings.put({"scan_roots": [str(world["dev"])]})
    sweep.run(llm_budget=0)
    r = client.get("/api/managed").json()
    assert r["implemented"] and {t["name"] for t in r["targets"]} == {"Alpha", "~/.claude"}
    assert len(r["pending"]) == 1
    tid = next(t["id"] for t in r["targets"] if t["name"] == "Alpha")
    assert client.post(f"/api/managed/{tid}/exclude").json()["implemented"]
    r = client.get("/api/managed").json()
    assert "Alpha" not in {t["name"] for t in r["targets"]} and len(r["excluded"]) == 1
    client.post("/api/managed/unexclude", json={"path": r["excluded"][0]})
    assert client.get("/api/managed").json()["excluded"] == []
