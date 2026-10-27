"""分解の再帰 の武器 decomposition_tree.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("分解の再帰", "decomposition_tree.py")


def base(tmp_path):
    g = graph(tmp_path)
    x = chain(g)
    p = g.add("component", "加熱部", {"obvious": True})
    c1 = g.add("component", "コイル", parent=p)
    c2 = g.add("component", "駆動回路", parent=p)
    ext = g.add("component", "釜", {"obvious": True})
    return g, x, p, c1, c2, ext


def test_external_relation_carried_by_a_child_is_fine(tmp_path, capsys):
    g, x, p, c1, c2, ext = base(tmp_path)
    g.link("relation", p, ext, predicate="加熱する")
    g.link("relation", c1, ext, predicate="電磁加熱する")
    g.link("relation", c1, c2, predicate="駆動される")   # 親の中どうし
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0
    (it,) = out["parents"]
    assert it["id"] == p and it["children"] == [c1, c2] and it["lost_relations"] == []


def test_external_relation_no_child_carries_is_reported(tmp_path, capsys):
    g, x, p, c1, c2, ext = base(tmp_path)
    rel = g.link("relation", p, ext, predicate="加熱する")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert out["parents"][0]["lost_relations"] == [{"link": rel, "other": ext, "predicate": "加熱する"}]
    rc, text, _ = run(m, capsys, tmp_path)
    assert "[関連が子に無い]" in text


def test_child_relation_to_a_part_of_the_other_end_counts(tmp_path, capsys):
    g, x, p, c1, c2, ext = base(tmp_path)
    inner = g.add("component", "釜の底", parent=ext)
    g.link("relation", p, ext, predicate="加熱する")
    g.link("relation", c1, inner, predicate="電磁加熱する")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0
    assert {i["id"] for i in out["parents"]} == {p, ext} and all(not i["lost_relations"] for i in out["parents"])


def test_requirement_allocated_to_parent_must_reach_a_child(tmp_path, capsys):
    g, x, p, c1, c2, ext = base(tmp_path)
    rq = g.add("requirement", "40 分で炊ける")
    link = g.link("allocates", rq, p)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert out["parents"][0]["lost_requirements"] == [{"link": link, "requirement": rq}]
    g.link("allocates", rq, c1)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["parents"][0]["lost_requirements"] == []


def test_refines_links_and_nested_levels_are_read(tmp_path, capsys):
    g, x, p, c1, c2, ext = base(tmp_path)
    c3 = g.add("component", "コイル巻線")
    g.link("refines", c1, c3)
    rc, text, _ = run(m, capsys, tmp_path)
    lines = text.splitlines()
    assert any(l.startswith("  ") and c1 in l for l in lines) and any(l.startswith("    ") and c3 in l for l in lines)
    rc, out, _ = run(m, capsys, tmp_path, "--id", c1, as_json=True)
    assert [i["id"] for i in out["parents"]] == [c1]


def test_options_under_a_decision_point_are_not_a_decomposition(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    rc, text, _ = run(m, capsys, tmp_path)
    assert rc == 0 and "分解している要素が無い" in text


def test_read_only(tmp_path, capsys):
    g, x, p, c1, c2, ext = base(tmp_path)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
