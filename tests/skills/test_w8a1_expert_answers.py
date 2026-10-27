"""専門家回答の管理 の武器 expert_answers.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("専門家回答の管理", "expert_answers.py")


def make(tmp_path):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "電熱の専門家 田中さんの回答", {"expert": "田中"})
    nt2 = g.add("record", "安全規格の専門家の回答", {"expert": "鈴木"})
    g.actor = "human"
    return g, x, nt, nt2


def test_which_decision_relies_on_which_answer(tmp_path, capsys):
    g, x, nt, nt2 = make(tmp_path)
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["100V"])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    by = {r["id"]: r for r in out["records"]}
    assert [d["id"] for d in by[nt]["relied_on_by"]] == [x["d"]]
    assert by[nt2]["relied_on_by"] == []
    assert out["unreferenced"] == [nt2]


def test_confirmed_without_any_answer_is_a_no_evidence_finding(tmp_path, capsys):
    g, x, nt, nt2 = make(tmp_path)
    g.set_state(x["cn"], "confirmed")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and [f["id"] for f in out["findings"]] == [f"no_evidence:{x['cn']}"]


def test_match_narrows_by_title_or_attributes(tmp_path, capsys):
    g, x, nt, nt2 = make(tmp_path)
    rc, out, _ = run(m, capsys, tmp_path, "--match", "田中", as_json=True)
    assert [r["id"] for r in out["records"]] == [nt]
    rc, out, _ = run(m, capsys, tmp_path, "--match", "鈴木", as_json=True)
    assert [r["id"] for r in out["records"]] == [nt2]


def test_verifies_is_shown(tmp_path, capsys):
    g, x, nt, nt2 = make(tmp_path)
    g.actor = "ai"
    g.link("verifies", nt, x["rq"])
    rc, text, _ = run(m, capsys, tmp_path)
    assert f"検証する要求: {x['rq']}" in text


def test_a_retired_answer_is_not_listed(tmp_path, capsys):
    g, x, nt, nt2 = make(tmp_path)
    g.set_state(nt2, "retired")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert [r["id"] for r in out["records"]] == [nt]


def test_read_only(tmp_path, capsys):
    g, x, nt, nt2 = make(tmp_path)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
