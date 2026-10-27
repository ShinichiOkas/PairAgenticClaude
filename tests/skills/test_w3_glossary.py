"""用語定義の書き方 の武器（lint_glossary.py）のテスト。"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parents[2] / "skills" / "scripts" / "用語定義の書き方" / "lint_glossary.py"
spec = importlib.util.spec_from_file_location("lint_glossary", P)
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

GOOD = """# 用語定義

## ログ

- 含む: アプリが処理中に書き出す時系列の記録
- 含まない: 画面に出る通知メッセージ
- 境界例: エラー時だけ画面にも出る記録は含む
- 上位語との差: 出力の一種だが、後から追える点で違う
- 確定: 師匠の回答「アプリが書く記録のこと」
"""


def test_good_definition_has_no_findings():
    assert g.lint(GOOD) == []


def test_one_sided_definition():
    t = GOOD.replace("- 含まない: 画面に出る通知メッセージ\n", "")
    f = g.lint(t)
    assert any("含まないが無い" in x for x in f)


def test_placeholder_is_empty():
    t = GOOD.replace("画面に出る通知メッセージ", "特になし")
    assert any("含まないが空" in x for x in g.lint(t))


def test_unconfirmed_and_ai_chosen():
    assert any("未確定" in x for x in g.lint(GOOD.replace("師匠の回答「アプリが書く記録のこと」", "未回答")))
    assert any("自分で選んだ疑い" in x for x in g.lint(GOOD.replace("師匠の回答「アプリが書く記録のこと」", "AI が自分で選んだ")))


def test_same_both_sides_and_missing_boundary():
    t = GOOD.replace("画面に出る通知メッセージ", "アプリが処理中に書き出す時系列の記録")
    assert any("同一" in x for x in g.lint(t))
    t2 = GOOD.replace("- 境界例: エラー時だけ画面にも出る記録は含む\n", "")
    assert any("境界例が無い" in x for x in g.lint(t2))


def test_duplicate_term_and_no_terms():
    assert any("重複" in x for x in g.lint(GOOD + "\n" + GOOD.split("\n", 2)[2]))
    assert g.lint("何もない") == ["[定義が無い] `## 語` の節が 1 つも無い"]


def test_continuation_lines_are_joined():
    t = GOOD.replace("- 含む: アプリが処理中に書き出す時系列の記録", "- 含む:\n  - アプリが処理中に書き出す時系列の記録")
    assert g.lint(t) == []


def test_new_writes_only_when_absent(tmp_path):
    out = tmp_path / "g.md"
    assert g.main(["new", "ログ", "結果", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").count("## ") == 2
    assert g.main(["new", "x", "--out", str(out)]) == 2
    # 雛形は未記入なので、そのまま lint すると指摘が出る
    assert g.main(["lint", str(out), "--strict"]) == 1


def test_new_preview_writes_nothing(tmp_path, capsys):
    assert g.main(["new", "ログ"]) == 0
    assert "下見" in capsys.readouterr().out
