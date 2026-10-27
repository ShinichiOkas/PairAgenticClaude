"""識別子の採番 の武器 id_ledger.py のテスト。"""
import json

from _w8a1_load import chain, db_path, graph, load, run, snapshot

m = load("識別子の採番", "id_ledger.py")


def test_clean_graph_has_no_problems_and_counts_by_prefix(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["problems"] == []
    by = {s["prefix"]: s for s in out["series"]}
    assert by["RQ"]["count"] == 1 and by["LC"]["max"] == 1 and by["D"]["count"] == 1
    assert by["L"]["count"] == by["L"]["max"]


def test_rejected_and_retired_ids_stay_and_are_not_a_problem(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    nt = g.add("record", "議事録")
    g.actor = "human"
    g.decide(x["d"], x["a"], evidence=[nt], conditions=["電源あり"])
    g.set_state(x["lc"], "retired")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0
    assert x["b"] in out["kept"]["rejected"] and x["lc"] in out["kept"]["retired"]


def test_a_missing_number_is_reported_when_an_event_was_removed(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    g.add("requirement", "二つ目")   # RQ2
    g.add("requirement", "三つ目")   # RQ3
    p = db_path(tmp_path)
    lines = p.read_text(encoding="utf-8").splitlines()
    kept = [l for l in lines if not (json.loads(l).get("op") == "create" and json.loads(l).get("id") == "RQ2")]
    assert len(kept) == len(lines) - 1
    p.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1
    assert {"id": "RQ2", "problem": "欠け", "detail": "RQ の採番は 3 まで進んでいる"} in out["problems"]


def test_an_id_that_does_not_match_the_kind_is_reported(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    p = db_path(tmp_path)
    last = max(json.loads(l)["seq"] for l in p.read_text(encoding="utf-8").splitlines())
    ev = {"seq": last + 1, "at": "2026-10-28T00:00:00Z", "actor": "ai", "op": "create", "id": "RQ9", "kind": "component",
          "title": "取り違え", "state": "hypothesis"}
    with p.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and any(p_["id"] == "RQ9" and p_["problem"] == "接頭辞違い" for p_ in out["problems"])


def test_option_letters_are_checked_against_the_decision_point(tmp_path, capsys):
    g = graph(tmp_path)
    x = chain(g)
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and x["c"] == "D1-C"


def test_read_only(tmp_path, capsys):
    g = graph(tmp_path)
    chain(g)
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    assert snapshot(tmp_path) == before
