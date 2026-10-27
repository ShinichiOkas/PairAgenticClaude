import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w4_load import load

m = load("待ちと保留の区別", "classify_waits.py")
NOW = dt.date(2026, 10, 27)


def test_structured_kinds_and_escalation():
    w = m.classify({"id": "1", "text": "x", "waiting_for": "Bさんのレビュー", "since": "2026-10-20"}, NOW, 3)
    assert (w["kind"], w["action"], w["age_days"]) == ("待ち", "上げる", 7)
    w = m.classify({"id": "1", "text": "x", "waiting_for": "B", "since": "2026-10-25"}, NOW, 3)
    assert w["action"] == "待つ"
    h = m.classify({"id": "2", "text": "y", "release_condition": "7日分のログが溜まる", "since": "2026-01-01"}, NOW, 3)
    assert h["kind"] == "保留" and h["action"] == "観測する（上げない）"
    both = m.classify({"id": "3", "text": "z", "waiting_for": "B", "release_condition": "c"}, NOW, 3)
    assert both["kind"] == "混在"


def test_keyword_inference_is_marked_and_ambiguous_is_flagged():
    a = m.classify({"id": "4", "text": "先方の返事待ち"}, NOW, 3)
    assert (a["kind"], a["how"]) == ("待ち", "推定")
    b = m.classify({"id": "5", "text": "実運用のデータが無く判定できない"}, NOW, 3)
    assert (b["kind"], b["how"]) == ("保留", "推定")
    c = m.classify({"id": "6", "text": "なんとなく止まっている"}, NOW, 3)
    assert c["kind"] == "判別不能" and "何があれば進むか" in c["advice"]
    d = m.classify({"id": "7", "text": "レビュー待ちだがデータも不明"}, NOW, 3)
    assert d["kind"] == "判別不能"


def test_wait_without_since(tmp_path):
    w = m.classify({"id": "8", "text": "t", "waiting_for": "B"}, NOW, 3)
    assert "since" in w["action"]


def test_cli_json_and_csv(tmp_path):
    j = tmp_path / "w.json"
    j.write_text(json.dumps([{"id": "1", "text": "t", "waiting_for": "B", "since": "2026-10-26"}]), encoding="utf-8")
    assert m.main([str(j), "--now", "2026-10-27"]) == 0
    c = tmp_path / "w.csv"
    c.write_text("id,text,waiting_for,release_condition,since\n1,何か,,,\n", encoding="utf-8")
    assert m.main([str(c), "--now", "2026-10-27"]) == 1
    assert m.main([str(tmp_path / "none.json")]) == 2
