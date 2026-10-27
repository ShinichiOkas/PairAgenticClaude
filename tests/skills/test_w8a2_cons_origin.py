import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w8a2_common import common_checks, graph, load, run, run_json

m = load("欠点の由来", "cons_origin.py")


def build(tmp_path, cons):
    g, db = graph(tmp_path)
    g.add("decision_point", "方式")
    g.add("option", "案 A", parent="D1", attrs={"cons": cons})
    g.add("option", "案 B", parent="D1")
    return db


def test_cons_without_origin_flagged(tmp_path, capsys):
    db = build(tmp_path, [{"text": "高い", "origin": "means"}, {"text": "遅い"}])
    rc, data = run_json(m, capsys, "--db", db)
    assert rc == 1
    assert data["tally"] == {"手段由来": 1, "本質的": 0, "由来なし": 1}
    assert [f["rule"] for f in data["findings"]] == ["cons_no_origin"]


def test_japanese_origin_words_and_clean(tmp_path, capsys):
    db = build(tmp_path, [{"text": "高い", "origin": "手段由来"}, {"text": "矛盾", "origin": "essential"}])
    rc, out, _ = run(m, capsys, "--db", db)
    assert rc == 0
    assert "[手段由来] 高い" in out and "[本質的] 矛盾" in out


def test_option_without_cons_is_skipped(tmp_path, capsys):
    db = build(tmp_path, [{"text": "x", "origin": "means"}])
    _, data = run_json(m, capsys, "--db", db)
    assert [o["id"] for o in data["options"]] == ["D1-A"]


def test_common(tmp_path, capsys, monkeypatch):
    db = build(tmp_path, [{"text": "遅い"}])
    common_checks(m, db, capsys, monkeypatch, tmp_path)
