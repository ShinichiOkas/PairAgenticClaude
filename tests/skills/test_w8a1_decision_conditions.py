"""決断の背景事情 の武器 decision_conditions.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("決断の背景事情", "decision_conditions.py")


def make(tmp_path):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "合意の記録")
    g.update(x["a"], attrs={"must": ["IH コイルを一次側に置く"], "must_not": ["ガス併用"]})
    g.actor = "human"
    return g, x, nt


def test_undecided_graph_has_no_decisions_and_no_findings(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["decisions"] == [] and out["findings"] == []


def test_decision_without_conditions_is_found(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.decide(x["d"], x["a"], evidence=[nt])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert [f["id"] for f in out["findings"]] == [f"no_conditions:{x['d']}"]
    assert out["decisions"][0]["conditions"] == []


def test_decision_with_conditions_lists_them_with_must_and_must_not(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["家庭用 100V 電源", "炊飯量は 5.5 合まで"], reason="静か")
    rc, text, _ = run(m, capsys, tmp_path)
    assert rc == 0
    assert "背景事情: 家庭用 100V 電源／炊飯量は 5.5 合まで" in text
    assert "must: IH コイルを一次側に置く" in text and "must_not: ガス併用" in text


def test_upstream_change_flags_the_decision_for_review(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["家庭用 100V 電源"])
    g.actor = "ai"
    g.update(x["is"], title="加熱が遅い（200V 地域を含む）")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    (d,) = out["decisions"]
    assert [r["downstream"] for r in d["needs_recheck"]] == [x["d"]]
    rc, text, _ = run(m, capsys, tmp_path)
    assert "見直し" in text


def test_id_option_narrows(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    d2 = g.add("decision_point", "保温方式")
    g.link("anchors", d2, x["is"])
    g.decide(x["d"], x["a"], evidence=[nt])
    rc, out, _ = run(m, capsys, tmp_path, "--id", d2, as_json=True)
    assert rc == 0 and out["decisions"] == []


def test_read_only(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.decide(x["d"], x["a"], evidence=[nt])
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
