"""バックトレース の武器 backtrace.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("バックトレース", "backtrace.py")


def test_element_reaches_decision_and_demand(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rc, out, _ = run(m, capsys, tmp_path, "--id", x["lc"], as_json=True)
    (it,) = out["items"]
    assert it["gaps"] == []
    assert x["a"] in it["decisions"] and x["rq"] in it["demands"] and x["cn"] in it["demands"]
    assert it["stops_at"] == [x["cn"]]
    assert [o["adopted"] for o in it["options"]] == [False]  # 決断前なので採用ではない


def test_adopted_option_is_flagged_adopted(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "議事録")
    g.actor = "human"
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["100V"])
    rc, out, _ = run(m, capsys, tmp_path, "--id", x["lc"], as_json=True)
    assert out["items"][0]["options"] == [{"id": x["a"], "decision_point": x["d"], "adopted": True, "decided": True}]


def test_element_without_a_decision_is_cut_at_a_dead_end(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    lc2 = g.add("component", "蓋")
    rq2 = g.add("requirement", "蓋が閉まる")
    g.link("allocates", rq2, lc2)
    rc, out, _ = run(m, capsys, tmp_path, "--id", lc2, as_json=True)
    assert rc == 1
    (it,) = out["items"]
    assert it["gaps"] == ["決断に届かない"]
    assert it["stops_at"] == [rq2] and it["decisions"] == [] and it["demands"] == [rq2]


def test_orphan_is_cut_on_both_and_obvious_is_exempt(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    lone = g.add("component", "迷子")
    sw = g.add("component", "電源スイッチ", {"obvious": True})
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    by = {i["id"]: i for i in out["items"]}
    assert by[lone]["gaps"] == ["決断に届かない", "要求・関心事に届かない"]
    assert by[sw]["gaps"] == [] and by[x["lc"]]["gaps"] == []
    assert rc == 1


def test_findings_on_the_chain_are_attached(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    g.actor = "human"
    g.set_state(x["rq"], "confirmed")
    rc, out, _ = run(m, capsys, tmp_path, "--id", x["lc"], as_json=True)
    rules = {f["id"] for f in out["items"][0]["findings"]}
    assert f"no_evidence:{x['rq']}" in rules and f"hyp_dep:{x['rq']}" in rules
    assert rc == 1


def test_default_targets_are_components_and_interfaces_only(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    ifc = g.add("interface", "投入口", {"obvious": True})
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert [i["id"] for i in out["items"]] == [ifc, x["lc"]]   # ID の自然順（IF1, LC1）


def test_read_only(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
