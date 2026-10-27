"""要素と決断の紐付け の武器 element_decision_link.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("要素と決断の紐付け", "element_decision_link.py")


def classes(out):
    return {e["id"]: e["class"] for e in out["elements"]}


def test_element_born_of_a_decision_is_classified_with_its_decision(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and classes(out) == {x["lc"]: "決断あり"}
    assert out["elements"][0]["decisions"] == [{"option": x["a"], "decision_point": x["d"], "status": "未決", "option_state": "hypothesis"}]


def test_adopted_and_rejected_status_follow_the_decision(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "議事録")
    g.actor = "human"
    g.decide(x["d"], x["b"], evidence=[nt], conditions=["圧力鍋"])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert out["elements"][0]["decisions"][0]["status"] == "不採用"
    assert rc == 0 and classes(out)[x["lc"]] == "決断あり"   # 不採用でも孤児ではない（要否の判断は on_dead の側）


def test_orphan_obvious_and_parent_only(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    lone = g.add("component", "迷子")
    sw = g.add("component", "電源スイッチ", {"obvious": True})
    parent = g.add("component", "筐体")
    child = g.add("component", "底板", parent=parent)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    got = classes(out)
    assert got[lone] == "孤児" and got[sw] == "自明" and got[child] == "決断なし（上流のみ）"
    assert got[parent] == "孤児"
    assert rc == 1


def test_decision_point_not_tied_to_an_issue_is_reported(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    d2 = g.add("decision_point", "保温方式")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and [f["id"] for f in out["orphan_decision_points"]] == [f"orphan:{d2}"]


def test_id_option_narrows_and_counts_are_given(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    g.add("component", "迷子")
    rc, out, _ = run(m, capsys, tmp_path, "--id", x["lc"], as_json=True)
    assert rc == 0 and out["counts"] == {"決断あり": 1}


def test_read_only(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
