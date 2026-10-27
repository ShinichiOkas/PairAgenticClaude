"""確定の根拠 の武器 evidence_audit.py のテスト（入口の探し方・読み取り専用・JSON と SQLite の両方を含む）。"""
import shutil
from pathlib import Path

import pytest
from _w8a1_load import ROOT, chain, graph, load, run, snapshot

m = load("確定の根拠", "evidence_audit.py")


def make(tmp_path, backend="json"):
    g = graph(tmp_path, backend=backend)
    x = chain(g)
    nt = g.add("record", "QAW の議事録")
    g.actor = "human"
    return g, x, nt


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_confirmed_without_evidence_is_found_with_chain(tmp_path, capsys, backend):
    g, x, nt = make(tmp_path, backend)
    g.set_state(x["cn"], "confirmed")
    rc, out, _ = run(m, capsys, tmp_path, backend=backend, as_json=True)
    assert rc == 1
    assert [f["id"] for f in out["findings"]] == [f"no_evidence:{x['cn']}"]
    assert out["chains"][x["cn"]][0]["id"] == x["cn"]
    assert out["confirmed"] == [{"id": x["cn"], "kind": "concern", "title": "炊き上がりまでの待ち時間", "evidence": []}]


def test_evidence_clears_the_finding(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.set_state(x["cn"], "confirmed", evidence=[nt])
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 0 and out["findings"] == []
    assert out["confirmed"][0]["evidence"] == [nt]


def test_hypothesis_below_confirmed_shows_the_chain_with_evidence(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.set_state(x["rq"], "confirmed", evidence=[nt])
    rc, text, _ = run(m, capsys, tmp_path)
    assert rc == 1
    assert f"[hyp_dep:{x['rq']}]" in text
    assert f"{x['a']} [仮説]" in text and f"根拠: {nt}" in text
    assert "根拠: なし" in text


def test_id_option_narrows_and_unknown_id_is_an_error(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.set_state(x["cn"], "confirmed")
    g.set_state(x["rq"], "confirmed")
    rc, out, _ = run(m, capsys, tmp_path, "--id", x["cn"], as_json=True)
    assert [f["target"] for f in out["findings"]] == [x["cn"]]
    rc, _, err = run(m, capsys, tmp_path, "--id", "ZZ99")
    assert rc == 2 and "ZZ99" in err


def test_read_only(tmp_path, capsys):
    g, x, nt = make(tmp_path)
    g.set_state(x["cn"], "confirmed")
    before = snapshot(tmp_path)
    run(m, capsys, tmp_path)
    run(m, capsys, tmp_path, as_json=True)
    assert snapshot(tmp_path) == before


def test_missing_db_is_exit_2(tmp_path, capsys):
    rc, _, err = run(m, capsys, tmp_path)
    assert rc == 2 and "DB が無い" in err
    assert not (tmp_path / "graph.jsonl").exists()


def test_core_not_found_lists_where_it_looked(tmp_path, capsys, monkeypatch):
    monkeypatch.setattr(m, "__file__", str(tmp_path / "a" / "b" / "x.py"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("USERPROFILE", str(tmp_path / "home"))
    monkeypatch.setenv("PAIR_AGENT_DESIGN_GRAPH", str(tmp_path / "nowhere.py"))
    rc = m.main(["--db", str(tmp_path / "g.jsonl")])
    err = capsys.readouterr().err
    assert rc == 2
    assert "PAIR_AGENT_DESIGN_GRAPH" in err and "nowhere.py" in err and "pair-agent" in err


def test_env_var_points_to_a_copy_of_the_core(tmp_path, capsys, monkeypatch):
    g, x, nt = make(tmp_path)
    g.set_state(x["cn"], "confirmed")
    core = tmp_path / "elsewhere" / "design_graph.py"
    core.parent.mkdir()
    shutil.copy(ROOT / "tools" / "design_graph.py", core)
    monkeypatch.setattr(m, "__file__", str(tmp_path / "a" / "b" / "x.py"))
    monkeypatch.setenv("PAIR_AGENT_DESIGN_GRAPH", str(core))
    rc, out, _ = run(m, capsys, tmp_path, as_json=True)
    assert rc == 1 and out["findings"][0]["rule"] == "no_evidence"
    assert Path(m.CORE.__file__) == core


def test_docstring_first_line_for_the_generator():
    first = (m.__doc__ or "").strip().splitlines()[0]
    assert first and first.endswith("。")
