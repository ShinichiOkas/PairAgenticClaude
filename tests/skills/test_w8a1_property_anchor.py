"""性質に結びつく決定 の武器 property_anchor.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("性質に結びつく決定", "property_anchor.py")


def test_decision_point_is_tied_to_the_concern_it_decides(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0
    (d,) = out["decision_points"]
    assert d["id"] == x["d"] and d["status"] == "性質あり" and d["issues"] == [x["is"]]
    assert d["properties"] == [{"id": x["cn"], "kind": "concern", "title": "炊き上がりまでの待ち時間", "state": "hypothesis", "weight": 5}]
    assert out["unreached_drivers"] == []
    rc, text, _ = run(m, capsys, tmp_path)
    assert "重み 5" in text


def test_decision_not_tied_to_an_issue_is_an_orphan(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    d2 = g.add("decision_point", "ボタンの色")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert {d["id"]: d["status"] for d in out["decision_points"]} == {x["d"]: "性質あり", d2: "孤児"}


def test_issue_that_reaches_no_concern_means_no_property(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    is2 = g.add("issue", "色が派手")
    d2 = g.add("decision_point", "ボタンの色")
    g.link("anchors", d2, is2)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert {d["id"]: d["status"] for d in out["decision_points"]}[d2] == "性質なし"


def test_quality_scenario_counts_as_a_property(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    d2 = g.add("decision_point", "保温の制御")
    is2 = g.add("issue", "保温中に煮詰まる")
    qs = g.add("qas", "保温 12 時間で食味が落ちない")
    g.link("anchors", d2, is2)
    g.link("affects", is2, qs)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    got = {d["id"]: d for d in out["decision_points"]}
    assert got[d2]["status"] == "性質あり" and got[d2]["properties"][0]["kind"] == "qas"


def test_driver_no_decision_reaches_is_reported(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    cn2 = g.add("concern", "安全", {"weight": 5})
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert out["unreached_drivers"] == [{"id": cn2, "title": "安全"}]


def test_decided_option_is_shown(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "議事録")
    g.actor = "human"
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["100V"])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert out["decision_points"][0]["decided"] == x["a"]


def test_read_only(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
