"""同時に効く規則の矛盾（J1）: 全体の規則どうしは全組を判定し、判定は使い回す。文案 → 反映でマスターと ~/.claude の同じ節を書き換え、取り消せる。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import write
from pamgr import changes, checks, conflicts, decide, inbox, llm, sweep, targets
from test_sweep import make_git_master, register_home, snapshot

RULES = ("# Pair Agent\n\n## 運転方針\n依頼を受けたら、聞き返さずに推奨を決めて着手する。\n\n"
         "## セッションの始め\nセッションの始めに自分から何も始めない。依頼が無ければ待つ。\n\n## 確認\n破壊的な操作の前は確認する。\n")


@pytest.fixture
def judged(world: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    for p in (world["master"] / "home-claude/CLAUDE.md", world["master"] / "home-claude/GEMINI.md", world["home"] / "CLAUDE.md"):
        write(p, RULES)
    make_git_master(world["master"])
    register_home(world)
    calls: list[tuple[str, str]] = []

    def fake_judge(a: dict, b: dict, model: str | None = None) -> tuple[checks.PairVerdict, str]:
        calls.append((a["anchor"], b["anchor"]))
        names = {a["anchor"], b["anchor"]}
        if names == {"運転方針", "セッションの始め"}:
            return checks.PairVerdict(relation="context_dependent", situation_a="main-agent", situation_b="session-start-no-request",
                                      reason="依頼の後か前かで分かれる"), "fake"
        return checks.PairVerdict(relation="unrelated", reason="別の話題"), "fake"

    monkeypatch.setattr(checks, "judge_pair", fake_judge)
    world["calls"] = calls  # type: ignore[assignment]
    return world


def test_all_global_pairs_judged_once_and_j1_raised(judged: dict) -> None:
    res = sweep.run(llm_budget=30)
    assert res["conflicts"]["j1"] == 1
    n_pairs = len(judged["calls"])
    assert n_pairs >= 3          # 全体の節どうしは全組（文字の類似で絞らない）
    items = [i for i in inbox.items() if i["kind"] == "J1"]
    assert len(items) == 1 and items[0]["title"] == "運転方針 × セッションの始め"
    assert "全プロジェクト" in items[0]["applies"]
    sweep.run(llm_budget=30)
    assert len(judged["calls"]) == n_pairs, "判定は使い回す"
    pv = sweep.run(dry_run=True)
    assert [i["kind"] for i in pv["inbox"]] == ["J1"]


def test_draft_then_decide_rewrites_master_and_home_and_undo(judged: dict, monkeypatch: pytest.MonkeyPatch) -> None:
    sweep.run(llm_budget=30)
    it = [i for i in inbox.items() if i["kind"] == "J1"][0]
    m, home = judged["master"], judged["home"]
    before = snapshot(m, home)

    def fake_draft(system: str, user: str, schema: type, **kw: object) -> tuple[decide.Draft, str]:
        return decide.Draft(a_text="## 運転方針\n適用する状況: main-agent（依頼を受けた後）\n依頼を受けたら、聞き返さずに推奨を決めて着手する。",
                            b_text="## セッションの始め\n適用する状況: session-start-no-request\nセッションの始めに自分から何も始めない。依頼が無ければ待つ。",
                            note="状況を足した"), "fake"

    monkeypatch.setattr(llm, "chat_structured", fake_draft)
    d = decide.draft(it["id"], "split")
    assert [e["side"] for e in d["edits"]] == ["a", "b"]
    out = decide.decide(it["id"], "split", d["edits"])
    assert out["status"] == "decided"
    mc = (m / "home-claude/CLAUDE.md").read_text(encoding="utf-8")
    assert "適用する状況: main-agent" in mc and "適用する状況: session-start-no-request" in mc
    assert (home / "CLAUDE.md").read_text(encoding="utf-8") == mc
    assert (m / "home-claude/GEMINI.md").read_text(encoding="utf-8") == mc, "マスターの GEMINI.md も同じ中身に保つ"
    assert mc.index("## 運転方針") < mc.index("## セッションの始め") < mc.index("## 確認")
    res = changes.undo(out["event"]["id"])
    decide.after_undo(res["refs"])
    assert snapshot(m, home) == before
    assert [i["status"] for i in inbox.items() if i["kind"] == "J1"] == ["open"]


def test_a_plus_b_merges_into_a_and_summarize_diff(judged: dict, monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    sweep.run(llm_budget=30)
    it = [i for i in inbox.items() if i["kind"] == "J1"][0]
    # 違いの要約（LLM 仮説）
    def fake_summary(system: str, user: str, schema: type, **kw: object) -> tuple[decide.DiffSummary, str]:
        return decide.DiffSummary(only_a=["推奨で着手"], only_b=["依頼が無ければ待つ"], shared=[], clash=["着手の向き"], note="場面で違う"), "fake"
    monkeypatch.setattr(llm, "chat_structured", fake_summary)
    s = client.post(f"/api/inbox/{it['id']}/summary").json()
    assert s["implemented"] and s["hypothesis"] and s["summary"]["only_a"] == ["推奨で着手"]

    # A ベースに B の要素を取り込む: SIDES=('replace','replace')・両側 edits が出る
    def fake_a_plus_b(system: str, user: str, schema: type, **kw: object) -> tuple[decide.Draft, str]:
        return decide.Draft(
            a_text="## 運転方針\n依頼を受けたら、聞き返さずに推奨を決めて着手する。\n\n補足: 依頼が無ければ待つ。",
            b_text="",
            note="B の『待つ』を A の末尾に補足として取り込み、B は空にした",
        ), "fake"
    monkeypatch.setattr(llm, "chat_structured", fake_a_plus_b)
    d = decide.draft(it["id"], "a_plus_b")
    assert [e["side"] for e in d["edits"]] == ["a", "b"]
    assert [e["action"] for e in d["edits"]] == ["replace", "replace"]
    out = decide.decide(it["id"], "a_plus_b", d["edits"])
    assert out["status"] == "decided"
    mc = (judged["master"] / "home-claude/CLAUDE.md").read_text(encoding="utf-8")
    assert "補足: 依頼が無ければ待つ。" in mc
    assert (judged["home"] / "CLAUDE.md").read_text(encoding="utf-8") == mc


def test_decide_api_starts_sweep_job_for_redistribute(judged: dict, monkeypatch: pytest.MonkeyPatch, client: TestClient) -> None:
    sweep.run(llm_budget=30)
    it = [i for i in inbox.items() if i["kind"] == "J1"][0]
    def fake_draft(system: str, user: str, schema: type, **kw: object) -> tuple[decide.Draft, str]:
        return decide.Draft(a_text="", b_text="", note="そのまま"), "fake"
    monkeypatch.setattr(llm, "chat_structured", fake_draft)
    d = client.post(f"/api/inbox/{it['id']}/draft", json={"option": "a"}).json()
    r = client.post(f"/api/inbox/{it['id']}/decide", json={"option": "a", "edits": d["edits"]}).json()
    assert r["implemented"] and r["status"] == "decided"
    assert "sweep_job" in r and r["sweep_job"], "決定カードで『再配布中』を出すために sweep_job が要る"
    # 後続テストの lock 衝突を避けるため、起こした sweep job の完了を待つ
    import time
    for _ in range(200):
        j = client.get(f"/api/jobs/{r['sweep_job']}").json()
        if j.get("state") != "running":
            break
        time.sleep(0.05)
    assert j.get("state") in ("done", "error"), j


def test_ok_dismisses_and_does_not_come_back(judged: dict) -> None:
    sweep.run(llm_budget=30)
    it = [i for i in inbox.items() if i["kind"] == "J1"][0]
    decide.decide(it["id"], "ok")
    sweep.run(llm_budget=30)
    assert [i for i in inbox.items() if i["kind"] == "J1"] == []


def test_llm_unavailable_keeps_pairs_pending(world: dict[str, Path]) -> None:
    write(world["home"] / "CLAUDE.md", RULES)
    make_git_master(world["master"])
    register_home(world)
    res = sweep.run(llm_budget=30)
    assert res["conflicts"]["remaining"] > 0 and "LLM" in res["conflicts"].get("stopped", "")
    assert any("未判定" in n for n in res["notes"])


def test_project_pairs_and_effective_api(judged: dict, client: TestClient) -> None:
    write(judged["dev"] / "Alpha/CLAUDE.md", "# Alpha\n\n## 着手\n依頼を受けたら、まず師匠に確認してから着手する。\n")
    targets.register([{"kind": "project", "path": str(judged["dev"] / "Alpha"), "name": "Alpha"}])
    cands, info = conflicts.candidates()
    assert info["projects"]["Alpha"] == 1
    assert any("Alpha" in c.applies for c in cands)
    tid = next(t["id"] for t in targets.list_targets() if t["name"] == "Alpha")
    r = client.get(f"/api/effective/{tid}").json()
    assert r["implemented"] and [len(L["units"]) for L in r["layers"]] == [4, 1]
