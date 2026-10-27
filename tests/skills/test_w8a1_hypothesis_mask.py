"""結論の顔をした仮説 の武器 hypothesis_mask.py のテスト。"""
from _w8a1_load import chain, graph, load, run, snapshot

m = load("結論の顔をした仮説", "hypothesis_mask.py")


def make(tmp_path):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "議事録")
    g.actor = "human"
    return g, x, nt


def test_no_confirmed_means_nothing_to_report(tmp_path, capsys):
    make(tmp_path)
    rc, text, _ = run(m, capsys, tmp_path)
    assert rc == 0 and "指摘なし" in text


def test_hypotheses_under_a_confirmed_conclusion_are_listed_with_depth(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.set_state(x["rq"], "confirmed", evidence=[nt])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    (c,) = out["conclusions"]
    assert c["id"] == x["rq"]
    got = {h["id"]: (h["depth"], h["direct"]) for h in c["hypotheses"]}
    assert got[x["a"]] == (1, True)
    assert got[x["d"]] == (2, False) and got[x["cn"]][1] is False


def test_hypothesis_ranking_counts_dependent_conclusions(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    rq2 = g.add("requirement", "もう一つの要求")
    g.link("derives", x["a"], rq2)
    g.set_state(x["rq"], "confirmed", evidence=[nt])
    g.set_state(rq2, "confirmed", evidence=[nt])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    top = out["to_confirm"][0]
    assert top["count"] == 2 and top["conclusions"] == [x["rq"], rq2]
    assert [e["count"] for e in out["to_confirm"]] == sorted((e["count"] for e in out["to_confirm"]), reverse=True)


def test_confirming_the_upstream_removes_the_finding(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.set_state(x["rq"], "confirmed", evidence=[nt])
    g.set_state(x["cn"], "confirmed", evidence=[nt])
    g.set_state(x["is"], "confirmed", evidence=[nt])
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["台所に IH 電源がある"])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["conclusions"] == []


def test_read_only_and_deterministic(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.set_state(x["rq"], "confirmed", evidence=[nt])
    before = snapshot(tmp_path)
    a = run(m, capsys, tmp_path)
    b = run(m, capsys, tmp_path)
    assert a == b and snapshot(tmp_path) == before
