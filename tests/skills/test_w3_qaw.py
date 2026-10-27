"""QAW の武器（question_graph.py）のテスト。"""
import importlib.util
import json
import sys
from pathlib import Path

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parents[2] / "skills" / "scripts" / "QAW" / "question_graph.py"
spec = importlib.util.spec_from_file_location("question_graph", P)
assert spec is not None and spec.loader is not None
q = importlib.util.module_from_spec(spec)
spec.loader.exec_module(q)

TXT = """\
# 問い
Q1 | 「ログ」とはアプリログのことですか？ | yes=Q2,Q3 ; no=Q4
Q2 | 形式は例示ですか厳密ですか？ | auto=Q5
Q3 | 保存先はファイルですか？ | *=Q6
Q4 | 画面表示のことですか？
Q5 | 区切り文字は何ですか？
Q6 | 保存先の上限はありますか？
Q7 | 結果はどこに出ますか？
"""


def load(text=TXT):
    qs, errs = q.parse(text)
    assert errs == []
    return qs


def test_lint_clean():
    assert q.lint(load()) == []


def test_lint_catches_problems():
    qs, _ = q.parse("A1 | 平叙文です | b=A9\nA1 | 重複ですか？\nA3 | 自分ですか？ | x=A3\n")
    f = "\n".join(q.lint(qs))
    assert "疑問形でない" in f and "未知の ID" in f and "ID 重複" in f and "自己参照" in f


def test_cycle_detected():
    qs, _ = q.parse("A | aですか？ | y=B\nB | bですか？ | y=A\n")
    assert any("循環" in x for x in q.lint(qs))


def test_order_puts_big_root_first_and_keeps_all_questions():
    qs = load()
    order = q.ask_order(qs)
    assert order[0] == ("Q1", 5)  # Q2,Q3,Q4 と、そこから確定する Q5,Q6
    assert [i for i, _ in order] == ["Q1", "Q7"]
    assert len(qs) == 7  # 絞らない


def test_status_band_and_cascade():
    qs = load()
    s = q.status(qs, {"Q1": "yes", "Q7": "ログ画面"})
    assert s["answered"] == ["Q1", "Q7"]
    assert s["determined"] == ["Q2", "Q3", "Q5", "Q6"]  # Q2 -> auto -> Q5, Q3 -> * -> Q6
    assert s["open"] == ["Q4"]  # yes では Q4 は消えない
    assert abs(s["band"] - 2 / 6) < 1e-9


def test_no_answer_path():
    s = q.status(load(), {"Q1": "no"})
    assert s["determined"] == ["Q4"] and s["answered"] == ["Q1"]
    assert "Q2" in s["open"]
    assert ("Q2", 2) in s["next"] or any(i == "Q2" for i, _ in s["next"])


def test_unknown_answer_id_reported():
    assert q.status(load(), {"Q99": "x"})["errors"]


def test_cli_and_json(tmp_path, capsys):
    f = tmp_path / "q.txt"
    f.write_text(TXT, encoding="utf-8")
    a = tmp_path / "a.json"
    a.write_text(json.dumps({"Q1": "yes"}), encoding="utf-8")
    assert q.main([str(f), "--answers", str(a)]) == 0
    out = capsys.readouterr().out
    assert "問いの総数: 7" in out and "A の帯域" in out
    j = tmp_path / "q.json"
    j.write_text(json.dumps([{"id": "A", "text": "aですか？", "resolves": {"y": ["B"]}}, {"id": "B", "text": "bですか？"}]), encoding="utf-8")
    assert q.main([str(j)]) == 0
    assert q.main([str(tmp_path / "none")]) == 2


def test_cli_returns_1_on_lint_error(tmp_path):
    f = tmp_path / "q.txt"
    f.write_text("A | 文です | y=Z\n", encoding="utf-8")
    assert q.main([str(f)]) == 1
