"""扱いの型の使い分け の武器（handling_ledger.py）のテスト。"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parents[2] / "skills" / "scripts" / "扱いの型の使い分け" / "handling_ledger.py"
spec = importlib.util.spec_from_file_location("handling_ledger", P)
assert spec is not None and spec.loader is not None
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)

LEDGER = """\
| 項目ID | 型 | 内容 | 解除条件 |
|---|---|---|---|
| R1 | スコープ外 | 今回は画面を作らない | |
| R2 | 延期 | 次スプリントで対応 | |
| R3 | 暫定 | 目標値 3 秒 | A が目標値を答えたら差し替える |
| R4 | 不可能 | 環境の制約で deps を満たす出力が存在しない | |
"""


def run(text, **kw):
    rows, errs = h.parse(text)
    return errs + h.lint(rows, **kw)


def test_clean_with_policy_allow():
    assert run(LEDGER, provisional="allow") == []


def test_policy_unknown_and_deny():
    assert any("方針未確認" in x for x in run(LEDGER))
    assert any("方針が暫定を許していない" in x for x in run(LEDGER, provisional="deny"))


def test_provisional_without_release():
    t = LEDGER.replace("A が目標値を答えたら差し替える", "")
    assert any("解除条件が無い" in x for x in run(t, provisional="allow"))


def test_provisional_vague_release():
    t = LEDGER.replace("A が目標値を答えたら差し替える", "いずれ確定したら")
    assert any("解除条件が曖昧" in x for x in run(t, provisional="allow"))


def test_unknown_type_and_empty_body():
    t = LEDGER + "| R5 | 保留 | あとで | |\n| R6 | 代案 | | |\n"
    f = run(t, provisional="allow")
    assert any("型が不明" in x and "R5" in x for x in f)
    assert any("内容が空" in x and "R6" in x for x in f)


def test_impossible_vs_could_not():
    t = LEDGER.replace("環境の制約で deps を満たす出力が存在しない", "時間が足りなくて実装できなかった")
    assert any("できなかったの混同" in x for x in run(t, provisional="allow"))


def test_silent_drop_detection():
    items = {"R1": "a", "R2": "b", "R7": "c"}
    rows, _ = h.parse(LEDGER)
    f = h.lint(rows, "allow", items)
    assert any("R7" in x and "黙って落ちている" in x for x in f)
    assert any("R3" in x and "項目に無いID" in x for x in f)


def test_duplicate_id():
    assert any("重複" in x for x in run(LEDGER + "| R1 | 延期 | x | |\n", provisional="allow"))


def test_summary():
    rows, _ = h.parse(LEDGER)
    s = h.summarize(rows)
    assert s["counts"]["暫定"] == 1 and s["blocking"] == ["R4"]
    assert s["open_provisional"] == [("R3", "A が目標値を答えたら差し替える")]


def test_cli(tmp_path, capsys):
    f = tmp_path / "l.md"
    f.write_text(LEDGER, encoding="utf-8")
    assert h.main([str(f), "--provisional", "allow", "--strict"]) == 0
    assert h.main([str(f), "--strict"]) == 1
    assert "下流が止まる" in capsys.readouterr().out
    assert h.main([str(tmp_path / "none.md")]) == 2
