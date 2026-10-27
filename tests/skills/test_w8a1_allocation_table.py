"""要求の割り付け の武器 allocation_table.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("要求の割り付け", "allocation_table.py")


def test_table_and_reverse_lookup(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    lc2 = g.add("component", "蓋")
    g.link("allocates", x["rq"], lc2)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["findings"] == []
    (row,) = out["table"]
    assert [t["id"] for t in row["targets"]] == [x["lc"], lc2]
    assert out["by_target"] == {x["lc"]: [x["rq"]], lc2: [x["rq"]]}


def test_unallocated_requirement_is_found(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rq2 = g.add("requirement", "保温できる")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and [f["id"] for f in out["findings"]] == [f"unallocated:{rq2}"]
    assert {r["id"]: r["targets"] for r in out["table"]}[rq2] == []
    rc, text, _ = run(m, capsys, tmp_path)
    assert "（割り付け先なし）" in text


def test_allocation_to_a_relation_counts(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rq2 = g.add("requirement", "釜と蓋の間から吹きこぼれない")
    lc2 = g.add("component", "蓋")
    rel = g.link("relation", x["lc"], lc2, predicate="受け止める")
    g.link("allocates", rq2, rel)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0
    got = {r["id"]: r["targets"] for r in out["table"]}[rq2]
    assert [t["id"] for t in got] == [rel] and got[0]["kind"] == "relation"


def test_retired_allocation_does_not_count(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    link = g.links_from(x["rq"], "allocates")[0]["id"]
    g.actor = "human"
    g.set_state(link, "retired")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and out["findings"][0]["target"] == x["rq"]


def test_id_option_narrows(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rq2 = g.add("requirement", "保温できる")
    rc, out, _ = run(m, capsys, tmp_path, "--id", x["rq"], as_json=True)
    assert rc == 0 and [r["id"] for r in out["table"]] == [x["rq"]]


def test_read_only(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
