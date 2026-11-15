"""正常系を端から端まで: 探索 → 登録 → 状況・差分 → 再配布 → サーベイ → 冗長の検査 → 一般化の検出 → 昇格 → 状況定義。"""

from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient


def _register_all(client: TestClient, dev: Path) -> list[dict]:
    cands = client.post("/api/targets/discover", json={"roots": [str(dev)], "depth": 2}).json()["candidates"]
    r = client.post("/api/targets", json={"targets": cands}).json()
    assert r["added"] == len(cands)
    return r["targets"]


def test_discover_finds_homes_and_projects(client: TestClient, world: dict[str, Path]) -> None:
    cands = client.post("/api/targets/discover", json={"roots": [str(world["dev"])], "depth": 2}).json()["candidates"]
    kinds = {(c["kind"], c["name"]) for c in cands}
    assert ("claude_home", "~/.claude") in kinds
    assert ("project", "Alpha") in kinds and ("project", "Beta") in kinds
    assert not any(c["name"] == "NotAProject" for c in cands)
    alpha = next(c for c in cands if c["name"] == "Alpha")
    assert "CLAUDE.md" in alpha["markers"] and ".pair-agent" in alpha["markers"]


def test_register_and_unregister(client: TestClient, world: dict[str, Path]) -> None:
    ts = _register_all(client, world["dev"])
    again = client.post("/api/targets", json={"targets": [{"path": t["path"], "kind": t["kind"]} for t in ts]}).json()
    assert again["added"] == 0
    tid = ts[0]["id"]
    assert client.delete(f"/api/targets/{tid}").json()["removed"] == tid
    assert client.delete(f"/api/targets/{tid}").status_code == 400


def test_status_diff_and_distribute(client: TestClient, world: dict[str, Path]) -> None:
    ts = _register_all(client, world["dev"])
    home = next(t for t in ts if t["kind"] == "claude_home")
    files = {f["dest_rel"]: f for f in client.get(f"/api/status/{home['id']}").json()["files"]}
    assert files["CLAUDE.md"]["state"] == "same"
    assert files["rules/core.md"]["state"] == "differs"           # 配布先で追記された（台帳なし → 向き不明）
    assert files["skills/retro/SKILL.md"]["state"] == "missing"
    d = client.get("/api/diff", params={"target_id": home["id"], "rel": "rules/core.md"}).json()["diff"]
    assert "+1 分以内に応答する。師匠の新しい追記。" in d

    plan = client.post("/api/distribute/plan", json={"scope": "global", "target_ids": [home["id"]]}).json()
    acts = {a["dest_rel"]: a for a in plan["actions"]}
    assert acts["skills/retro/SKILL.md"]["action"] == "create" and acts["skills/retro/SKILL.md"]["selected_default"]
    assert acts["rules/core.md"]["action"] == "conflict" and not acts["rules/core.md"]["selected_default"]
    assert "CLAUDE.md" not in acts and plan["skipped_same"] >= 1
    chosen = [a["id"] for a in plan["actions"] if a["selected_default"]]
    res = client.post("/api/distribute/apply", json={"plan_id": plan["plan_id"], "action_ids": chosen}).json()
    assert len(res["applied"]) == len(chosen)
    assert (world["home"] / "skills/retro/SKILL.md").read_text(encoding="utf-8").startswith("---\nname: retro")
    assert "師匠の新しい追記" in (world["home"] / "rules/core.md").read_text(encoding="utf-8")  # 改変は潰さない

    # 台帳ができた後: マスターを変えると master-ahead、配布先を変えると target-ahead
    (world["master"] / "home-claude/skills/retro/SKILL.md").write_text("---\nname: retro\n---\n更新\n", encoding="utf-8")
    st = {f["dest_rel"]: f["state"] for f in client.get(f"/api/status/{home['id']}").json()["files"]}
    assert st["skills/retro/SKILL.md"] == "master-ahead"
    plan2 = client.post("/api/distribute/plan", json={"scope": "global", "target_ids": [home["id"]]}).json()
    a = next(x for x in plan2["actions"] if x["dest_rel"] == "skills/retro/SKILL.md")
    (world["home"] / "skills/retro/SKILL.md").write_text("配布先で書き換え\n", encoding="utf-8")
    res2 = client.post("/api/distribute/apply", json={"plan_id": plan2["plan_id"], "action_ids": [a["id"]]}).json()
    assert res2["applied"] == [] and "変わった" in res2["skipped"][0]["reason"]   # 計画の後の変更は潰さない
    st = {f["dest_rel"]: f["state"] for f in client.get(f"/api/status/{home['id']}").json()["files"]}
    assert st["skills/retro/SKILL.md"] == "diverged"


def test_overwrite_makes_backup(client: TestClient, world: dict[str, Path]) -> None:
    ts = _register_all(client, world["dev"])
    home = next(t for t in ts if t["kind"] == "claude_home")
    plan = client.post("/api/distribute/plan", json={"scope": "global", "target_ids": [home["id"]]}).json()
    a = next(x for x in plan["actions"] if x["dest_rel"] == "rules/core.md")
    res = client.post("/api/distribute/apply", json={"plan_id": plan["plan_id"], "action_ids": [a["id"]]}).json()
    assert res["applied"] and res["backup_dir"]
    backup = Path(res["backup_dir"]) / home["id"] / "rules/core.md"
    assert "師匠の新しい追記" in backup.read_text(encoding="utf-8")
    assert (world["home"] / "rules/core.md").read_text(encoding="utf-8") == (world["master"] / "home-claude/rules/core.md").read_text(encoding="utf-8")


def test_adopt_target_version_into_master(client: TestClient, world: dict[str, Path]) -> None:
    ts = _register_all(client, world["dev"])
    home = next(t for t in ts if t["kind"] == "claude_home")
    client.post("/api/status/adopt", json={"target_id": home["id"], "rel": "rules/core.md"})
    assert "師匠の新しい追記" in (world["master"] / "home-claude/rules/core.md").read_text(encoding="utf-8")
    st = {f["dest_rel"]: f["state"] for f in client.get(f"/api/status/{home['id']}").json()["files"]}
    assert st["rules/core.md"] == "same"


def test_survey_and_redundancy(client: TestClient, world: dict[str, Path]) -> None:
    _register_all(client, world["dev"])
    sv = client.post("/api/survey/run").json()
    units = sv["units"]
    assert sv["summary"]["by_scope"]["master"] > 0 and sv["summary"]["by_scope"]["project"] > 0
    assert any(u["kind"] == "skill" and u["name"] == "alpha-db" and u["scope"] == "project" for u in units)
    assert any(u["kind"] == "skill" and u["name"] == "ui-first" and u["scope"] == "user" for u in units)
    sec = [u for u in units if u["kind"] == "rule-section" and u["anchor"] == "運転方針"]
    assert {u["scope"] for u in sec} >= {"master", "global", "project"}
    one = client.get(f"/api/survey/unit/{units[0]['id']}").json()["unit"]
    assert one["text"]

    job = client.post("/api/checks/run", json={"mode": "redundancy"}).json()["job_id"]
    j: dict = {}
    for _ in range(200):
        j = client.get(f"/api/jobs/{job}").json()
        if j["state"] != "running":
            break
        time.sleep(0.05)
    assert j["state"] == "done", j
    red = client.get("/api/checks").json()["redundancy"]
    assert red["copies"] >= 1                                         # 配布された写しは冗長に数えない
    assert any(v["name"].endswith("core.md › 応答") for v in red["variants"])  # 改変された写し


def test_generalize_detection_and_promote(client: TestClient, world: dict[str, Path]) -> None:
    from pamgr import generalize

    _register_all(client, world["dev"])
    client.post("/api/survey/run")
    text = (world["dev"] / "Alpha/.pair-agent/skills/alpha-db.md").read_text(encoding="utf-8")
    terms = {f["term"]: f["kind"] for f in generalize.detect(text)}
    assert terms.get("Alpha") == "プロジェクト名"
    assert terms.get("ALPHA_WORK_DIR") == "固有の環境変数"
    assert any(k == "絶対パス" for k in terms.values())
    assert generalize.remaining("この製品では、データルートの環境変数の下に置く。\n```\nALPHA_WORK_DIR\n```\n") == []

    r = client.post("/api/generalize/promote", json={"text": "---\nname: db-place\n---\n本文\n", "scope": "global", "name": "db-place"}).json()
    assert Path(r["written"]).read_text(encoding="utf-8").startswith("---\nname: db-place")
    dup = client.post("/api/generalize/promote", json={"text": "x", "scope": "global", "name": "db-place"})
    assert dup.status_code == 400
    nosub = client.post("/api/generalize/promote", json={"text": "x", "scope": "user", "name": "y"})
    assert nosub.status_code == 400 and "サブモジュール" in nosub.json()["error"]


def test_situations_seed_and_save(client: TestClient, world: dict[str, Path]) -> None:
    s = client.get("/api/situations").json()["situations"]
    assert any(x["id"] == "main-agent" for x in s)
    r = client.post("/api/situations", json={"id": "gui-dev", "name": "GUI を作っている", "definition": "画面がある", "signals": ["static/"]})
    assert any(x["id"] == "gui-dev" for x in r.json()["situations"])
    assert (world["master"] / "situations/situations.yaml").is_file()
    assert client.post("/api/situations", json={"id": "Bad ID", "name": "x"}).status_code == 400


def test_settings_roundtrip_and_llm_unconfigured(client: TestClient, world: dict[str, Path], monkeypatch) -> None:
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    s = client.put("/api/settings", json={"model_judge": "", "scan_depth": 9}).json()["settings"]
    assert s["scan_depth"] == 5
    client.post("/api/survey/run")
    r = client.post("/api/checks/run", json={"mode": "conflict"})
    assert r.status_code == 400 and "モデル" in r.json()["error"]
