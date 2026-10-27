import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("一モデル一要素種", "model_element_kinds.py")


def build(tmp_path, mixed):
    g, db = graph(tmp_path)
    for t in ("制御", "計測", "通知"):
        g.add("component", t)
    g.add("interface", "温度 API")
    g.add("component", "別の図の部品")
    g.add("component", "別の図の部品 2")
    g.link("relation", "LC1", "LC2", predicate="を読む")
    g.link("relation", "LC2", "IF1" if mixed else "LC3", predicate="を呼ぶ")
    g.link("relation", "LC4", "LC5", predicate="を包む")
    return db


def test_no_model_infers_mixed_kinds_with_distinct_id(tmp_path, capsys):
    db = build(tmp_path, mixed=True)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert [p["id"] for p in data["problems"]] == ["inferred_mixed_kinds:IF1"]
    assert "図が DB に無いので関連のつながりから推定した" in data["problems"][0]["message"]
    mixed = [x for x in data["models"] if x["mixed"]]
    assert mixed[0]["kinds"] == ["component", "interface"]
    assert data["findings"] == []  # 述語は付いている、MO が無いので中核の mixed_kinds も出ない
    rc2, out, _ = run(m, capsys, "--db", db)
    assert rc2 == 1 and "図が DB に無いので関連のつながりから推定した" in out


def test_with_model_uses_core_mixed_kinds(tmp_path, capsys):
    db = build(tmp_path, mixed=True)
    g, _ = graph(tmp_path)
    mo = g.add("model", "混ざった図", {"viewpoint": "logical"})
    g.link("shows", mo, "LC1")
    g.link("shows", mo, "IF1")
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert data["problems"] == []  # 連結成分の推定は出さない
    assert not any(x["mixed"] for x in data["models"])
    ids = [f["id"] for f in data["findings"] if f["rule"] == "mixed_kinds"]
    assert len(ids) == 1 and ids[0].startswith("mixed_kinds")
    assert data["findings"][0]["target"] == mo


def test_with_model_single_kind_and_whiteboard_are_clean(tmp_path, capsys):
    db = build(tmp_path, mixed=True)
    g, _ = graph(tmp_path)
    ok = g.add("model", "論理の図", {"viewpoint": "logical"})
    g.link("shows", ok, "LC1")
    wb = g.add("model", "ホワイトボード", {"viewpoint": "logical", "whiteboard": True})
    g.link("shows", wb, "LC1")
    g.link("shows", wb, "IF1")
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0 and data["problems"] == [] and data["findings"] == []


def test_single_kind_models_are_clean(tmp_path, capsys):
    db = build(tmp_path, mixed=False)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0 and len(data["models"]) == 2 and data["problems"] == []


def test_id_selects_the_model(tmp_path, capsys):
    db = build(tmp_path, mixed=True)
    rc, data = run_json(m, capsys, "--db", db, "LC4")
    assert rc == 0 and [x["elements"] for x in data["models"]] == [["LC4", "LC5"]]
    rc2, _, err = run(m, capsys, "--db", db, "XX9")
    assert rc2 == 2 and "無い ID" in err


def test_allocation_figure_is_the_exception(tmp_path, capsys):
    db = build(tmp_path, mixed=False)
    g, _ = graph(tmp_path)
    g.add("requirement", "速い")
    g.link("allocates", "RQ1", "LC1")
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 0 and data["allocations"][0]["src"] == "RQ1"


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, mixed=True)
    common_checks(m, db, capsys, monkeypatch, tmp_path)
