import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, reopen, run, run_json

m = load("重みのラベル付け", "weight_label.py")


def build(tmp_path):
    g, db = graph(tmp_path)
    g.add("concern", "待ち時間", attrs={"weight": 5})
    g.add("concern", "見た目", attrs={"weight": 2, "if_not_met": "印象が悪いだけ"})
    g.add("concern", "重みなし")
    g.add("record", "顧客の発言: 30 分を超えたら返品")
    reopen(db, "human").link("evidence", "CN2", "NT1")
    return db


def test_missing_weight_flagged_and_hypothesis_weights_listed(tmp_path, capsys):
    db = build(tmp_path)
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert [f["id"] for f in data["findings"]] == ["no_weight:CN3"]
    assert data["hypothesis_weights"] == ["CN1"]  # 根拠の記録を指さない重み


def test_grounded_weight_and_reason_shown(tmp_path, capsys):
    db = build(tmp_path)
    _, out, _ = run(m, capsys, "--db", db)
    assert "達成されなかったとき: 印象が悪いだけ" in out and "根拠: NT1" in out
    assert "CN1" in out and "← 仮説の重み" in out


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path)
    common_checks(m, db, capsys, monkeypatch, tmp_path)
