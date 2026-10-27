"""判定可能な仕様の書き方 の武器（procedure_matrix.py）のテスト。"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parents[2] / "skills" / "scripts" / "判定可能な仕様の書き方" / "procedure_matrix.py"
spec = importlib.util.spec_from_file_location("procedure_matrix", P)
pm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pm)

GOOD = """\
## S1: 外部パッケージに依存しない

- 満たしている: ソース中のどの import も標準ライブラリか自パッケージを指す
- 手続き: ast で全 import 文を走査し、標準ライブラリ一覧と照合する
- 偽陽性: 標準ライブラリ一覧に無い新しい標準モジュールを誤って外部と判定する
- 偽陰性: importlib.import_module に文字列で渡す動的 import は見えない
- 検出できない範囲: 動的 import（文字列で組み立てた名前）
- 等価置換: なし
"""


def test_good_matrix_clean():
    assert pm.lint(GOOD) == []


def test_substitution_of_feasibility_is_flagged():
    t = GOOD.replace("ソース中のどの import も標準ライブラリか自パッケージを指す", "隔離環境で実行して落ちなければ合格")
    assert any("実施可能性の代用" in x for x in pm.lint(t))


def test_missing_backward_direction():
    t = GOOD.replace("- 偽陰性: importlib.import_module に文字列で渡す動的 import は見えない\n", "")
    assert any("偽陰性が無い" in x for x in pm.lint(t))


def test_false_negative_listed_but_range_missing():
    t = GOOD.replace("- 検出できない範囲: 動的 import（文字列で組み立てた名前）\n", "")
    assert any("検出できない範囲が無い" in x for x in pm.lint(t))


def test_false_negative_none_needs_reason():
    t = GOOD.replace("importlib.import_module に文字列で渡す動的 import は見えない", "なし")
    assert any("根拠が無い" in x for x in pm.lint(t))
    t2 = GOOD.replace("importlib.import_module に文字列で渡す動的 import は見えない", "なし。全 import 構文は ast に現れ、仕様も動的 import を禁じている")
    assert not any("根拠が無い" in x for x in pm.lint(t2))


def test_equivalence_needs_counterexamples():
    t = GOOD.replace("- 等価置換: なし", "- 等価置換: はい\n- 反例: 遅延 import")
    assert any("等価の根拠" in x for x in pm.lint(t))
    t2 = GOOD.replace("- 等価置換: なし", "- 等価置換: はい\n- 反例: 遅延 import；try/except の import")
    assert not any("等価の根拠" in x for x in pm.lint(t2))


def test_spec_coverage():
    f = pm.lint(GOOD, ["S1", "S2"])
    assert any("S2" in x and "手続きが無い" in x for x in f)
    assert any("S3" in x and "仕様に無い" in x for x in pm.lint(GOOD + "\n## S3: x\n", ["S1"]))


def test_new_then_lint_flags_everything(tmp_path):
    spec_f = tmp_path / "s.txt"
    spec_f.write_text("S1: 外部パッケージに依存しない\nS2: 1 秒以内に応答する\n", encoding="utf-8")
    out = tmp_path / "m.md"
    assert pm.main(["new", str(spec_f), "--out", str(out)]) == 0
    assert pm.main(["new", str(spec_f), "--out", str(out)]) == 2
    assert pm.main(["lint", str(out), "--spec", str(spec_f), "--strict"]) == 1
    assert len(pm.parse(out.read_text(encoding="utf-8"))) == 2


def test_cli_missing_file(tmp_path):
    assert pm.main(["lint", str(tmp_path / "x.md")]) == 2
