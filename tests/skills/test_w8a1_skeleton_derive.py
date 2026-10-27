"""骨格の導出 の武器 skeleton_derive.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("骨格の導出", "skeleton_derive.py")


def skeleton(tmp_path):
    """ミニマル定義の語から導いた骨格: 米 —炊く→ 釜、加熱 —熱する→ 釜。要素はどれも決断を持たない。"""
    g = graph(tmp_path)
    mn = g.add("requirement", "米を水と熱で炊く")
    a = g.add("component", "加熱")
    b = g.add("component", "釜")
    for c in (a, b):
        g.link("derives", mn, c)
    g.link("relation", a, b, predicate="熱する")
    return g, mn, a, b


def test_skeleton_elements_and_triples(tmp_path, capsys):
    g, mn, a, b = skeleton(tmp_path)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0
    assert {e["id"]: e["origin"] for e in out["elements"]} == {a: "骨格", b: "骨格"}
    assert out["elements"][0]["derives_from"] == [mn]
    assert [(t["subject"], t["predicate"], t["object"]) for t in out["relations"]] == [(a, "熱する", b)]
    rc, text, _ = run(m, capsys, tmp_path)
    assert f"{a} —熱する→ {b}" in text


def test_relation_without_predicate_is_incomplete(tmp_path, capsys):
    g, mn, a, b = skeleton(tmp_path)
    c = g.add("component", "蓋")
    g.link("derives", mn, c)
    rel = g.link("relation", b, c)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and [f["id"] for f in out["no_predicate"]] == [f"no_predicate:{rel}"]


def test_element_on_no_line_and_orphan_are_pointed_out(tmp_path, capsys):
    g, mn, a, b = skeleton(tmp_path)
    c = g.add("component", "迷子")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and out["orphans"] == [c] and out["isolated"] == [c]


def test_added_element_is_classified_by_its_origin(tmp_path, capsys):
    g, mn, a, b = skeleton(tmp_path)
    x = chain(g)       # 決断から生まれた LC
    child = g.add("component", "底板", parent=b)
    sw = g.add("component", "電源スイッチ", {"obvious": True})
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    got = {e["id"]: e["origin"] for e in out["elements"]}
    assert got[x["lc"]] == "決断由来" and got[child] == "親から" and got[sw] == "自明" and got[a] == "骨格"


def test_single_component_is_not_called_isolated(tmp_path, capsys):
    g = graph(tmp_path)
    mn = g.add("requirement", "炊く")
    a = g.add("component", "釜")
    g.link("derives", mn, a)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["isolated"] == []


def test_read_only(tmp_path, capsys):
    g, mn, a, b = skeleton(tmp_path)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
