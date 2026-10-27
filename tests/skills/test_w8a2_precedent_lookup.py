import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("判例の照合", "precedent_lookup.py")


def build(tmp_path):
    g, db = graph(tmp_path)
    g.add("decision_point", "通信方式")
    g.add("option", "Bluetooth", parent="D1", attrs={"viewpoint": "電力", "cons": [{"text": "距離が短い", "origin": "essential"}]})
    g.add("option", "有線", parent="D1", attrs={"viewpoint": "確実さ"})
    g.add("option", "Wi-Fi", parent="D1", attrs={"viewpoint": "速度"})
    g.add("decision_point", "保存先")
    g.add("option", "ローカル", parent="D2")
    g.add("option", "クラウド", parent="D2")
    h = reopen(db, "human")
    h.decide("D1", "D1-B", conditions=["工場内は電波が悪い"])
    h.decide("D2", "D2-A", conditions=["オフラインで使う"])
    h.set_state("D2-B", "retired", reason="運用で使わない")
    return db


def test_default_lists_rejected_and_retired_with_conditions(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0
    ids = [p["id"] for p in data["precedents"]]
    assert ids == ["D1-A", "D1-C", "D2-B"]
    first = data["precedents"][0]
    assert first["adopted"] == "D1-B" and first["conditions"] == ["工場内は電波が悪い"]
    assert first["reason"] == "D1 で D1-B を採用"
    assert data["precedents"][2]["reason"] == "運用で使わない"


def test_terms_narrow_by_condition_and_are_anded(tmp_path, capsys):
    db = build(tmp_path)
    _, data = run_json(m, capsys, "--db", db, "電波")
    assert [p["id"] for p in data["precedents"]] == ["D1-A", "D1-C"]
    _, data = run_json(m, capsys, "電波", "bluetooth", "--db", db)
    assert [p["id"] for p in data["precedents"]] == ["D1-A"]


def test_state_option(tmp_path, capsys):
    db = build(tmp_path)
    _, data = run_json(m, capsys, "--db", db, "--state", "retired")
    assert [p["id"] for p in data["precedents"]] == ["D2-B"]
    _, data = run_json(m, capsys, "--db", db, "--state", "confirmed")
    assert [p["id"] for p in data["precedents"]] == ["D1-B", "D2-A"]
    rc, out, _ = run(m, capsys, "--db", db, "存在しない語")
    assert rc == 0 and "該当なし" in out


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path, "電波")
