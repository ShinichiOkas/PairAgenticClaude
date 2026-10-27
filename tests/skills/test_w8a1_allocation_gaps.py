"""割り付けの課題化 の武器 allocation_gaps.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("割り付けの課題化", "allocation_gaps.py")


def test_chain_requirement_to_component_to_platform(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    cpu = g.add("component", "マイコン")
    g.link("allocates", x["lc"], cpu)
    rc, out, _ = run(m, capsys, tmp_path, "--platform", cpu, as_json=True)
    assert out["chains"] == [[x["rq"], x["lc"], cpu]]
    assert out["no_platform"] == [] and out["no_requirement"] == []


def test_chain_that_stops_short_of_the_platform_is_a_candidate(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    cpu = g.add("component", "マイコン")
    rc, out, _ = run(m, capsys, tmp_path, "--platform", cpu, as_json=True)
    assert rc == 1 and out["no_platform"] == [x["lc"]]
    rc, text, _ = run(m, capsys, tmp_path, "--platform", cpu)
    assert "実装先が未定" in text


def test_without_platform_option_the_section_is_not_judged(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["no_platform"] == []


def test_element_nobody_allocated_and_unallocated_requirement(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rq2 = g.add("requirement", "保温できる")
    lc2 = g.add("component", "保温ヒーター")
    sw = g.add("component", "電源スイッチ", {"obvious": True})
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert [f["target"] for f in out["unallocated"]] == [rq2]
    assert out["no_requirement"] == [lc2]       # 自明なスイッチは除く
    assert [f["target"] for f in out["orphans"]] == [lc2]
    assert sw not in out["no_requirement"]


def test_allocation_to_a_relation_continues_to_its_ends(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    lc2 = g.add("component", "蓋")
    rel = g.link("relation", x["lc"], lc2, predicate="受け止める")
    rq2 = g.add("requirement", "吹きこぼれない")
    g.link("allocates", rq2, rel)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert [rq2, x["lc"]] in out["chains"] and [rq2, lc2] in out["chains"]


def test_read_only(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
