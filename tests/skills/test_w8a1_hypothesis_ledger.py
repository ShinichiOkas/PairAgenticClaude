"""AI出力の仮説扱い の武器 hypothesis_ledger.py のテスト。"""
import json

from _w8a1_load import chain, db_path, graph, load, run, snapshot

m = load("AI出力の仮説扱い", "hypothesis_ledger.py")


def append_raw(tmp_path, **ev):
    """人の操作を経ずに状態が変わった DB（権限の外で書き換わった疑い）を作る。"""
    p = db_path(tmp_path)
    last = max(json.loads(l)["seq"] for l in p.read_text(encoding="utf-8").splitlines() if l.strip())
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps({"seq": last + 1, "at": "2026-10-28T00:00:00Z", **ev}, ensure_ascii=False) + "\n")


def test_everything_the_ai_wrote_is_hypothesis_only(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0
    assert out["counts"]["touched_by_human"] == 0 and out["counts"]["exceptions"] == 0
    assert {h["id"] for h in out["hypothesis_only"]} >= {x["cn"], x["rq"], x["lc"], x["d"], x["a"]}
    assert all(h["created_by"] == "ai" and h["human_ops"] == 0 for h in out["hypothesis_only"])


def test_what_a_human_confirmed_or_rejected_is_listed_with_the_operation(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "議事録")
    g.actor = "human"
    g.set_state(x["cn"], "confirmed", evidence=[nt])
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["電源あり"])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0
    touched = {t["id"]: t for t in out["touched_by_human"]}
    assert touched[x["cn"]]["state"] == "confirmed" and touched[x["cn"]]["by"] == "human"
    assert touched[x["b"]]["state"] == "rejected" and touched[x["b"]]["by"] == "human"
    assert x["cn"] not in {h["id"] for h in out["hypothesis_only"]}


def test_a_state_change_without_a_human_is_an_exception(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    append_raw(tmp_path, actor="ai", op="state", id=x["lc"], state="confirmed")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert [e["id"] for e in out["exceptions"]] == [x["lc"]]
    assert "人の操作が履歴に無い" in out["exceptions"][0]["reason"]


def test_an_evidence_link_not_made_by_a_human_is_an_exception(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "議事録")
    append_raw(tmp_path, actor="ai", op="link", id="L99", kind="evidence", src=x["lc"], dst=nt, state="confirmed", seen=1)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and out["exceptions"][0]["id"] == "L99"


def test_read_only(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
