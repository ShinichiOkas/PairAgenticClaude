import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load(skill, name):
    p = ROOT / "skills" / "scripts" / skill / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"w5_{name}", p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


la = load("エビデンスの設計", "lint_assurance")

TABLE = """# 設計保証

| 項目 | 主張 | エビデンス |
|---|---|---|
| S-1 | 標準ライブラリのみ | `python check_imports.py stdlib src/` の出力: 違反 0 件 |
| S-2 | 層構造を守る | レビューしました |
| S-3 | 縮退はログを出す | |
| S-4 | 例外は握りつぶさない | 問題ない |

## 保証しなかったこと
S-9 は確かめられなかった。
"""


def by_id(text):
    claims, issues = la.lint(text)
    return claims, {(i["code"]) for i in issues}, issues


def test_table_claims_are_parsed():
    claims, _, _ = by_id(TABLE)
    assert [c["id"] for c in claims] == ["S-1", "S-2", "S-3", "S-4"]
    assert claims[0]["evidence"].startswith("`python")


def test_each_defect_kind_is_reported_on_its_own_row():
    _, _, issues = by_id(TABLE)
    got = {(i["code"], i["line"]) for i in issues}
    assert ("weak-evidence", 6) in got
    assert ("no-evidence", 7) in got
    assert ("weak-evidence", 8) in got
    assert not [i for i in issues if i["line"] == 5]


def test_machine_output_evidence_is_accepted():
    ok = TABLE.replace("レビューしました", "pytest の出力 12 件通過").replace("| S-3 | 縮退はログを出す | |", "| S-3 | x | 出力 4 件中 4 件 |").replace("問題ない", "grep 結果 0 件")
    _, _, issues = by_id(ok)
    assert [i for i in issues if i["severity"] == "error"] == []


def test_section_format():
    t = ("## S-1 依存\n- 主張: 標準のみ\n- エビデンス: `grep -r import src/` 結果 0 件\n\n"
         "## S-2 ログ\n- 主張: 縮退は記録\n- エビデンス: 確認済み\n\n## 確かめられなかったこと\nなし\n")
    claims, _, issues = by_id(t)
    assert [c["id"] for c in claims] == ["S-1", "S-2"]
    assert [i["code"] for i in issues if i["severity"] == "error"] == ["weak-evidence"]


def test_missing_unverified_section_warns():
    t = "| 項目 | 主張 | エビデンス |\n|---|---|---|\n| S-1 | a | pytest 3 件 |\n"
    assert "no-unverified-section" in by_id(t)[1]


def test_no_claims_is_error_and_cli_exit_codes(tmp_path):
    p = tmp_path / "a.md"
    p.write_text("ただの文章", encoding="utf-8")
    assert la.main([str(p)]) == 1
    p.write_text(TABLE, encoding="utf-8")
    assert la.main([str(p)]) == 1
    p.write_text(TABLE.replace("レビューしました", "pytest 3 件").replace("| S-3 | 縮退はログを出す | |", "| S-3 | x | 出力 1 件 |").replace("問題ない", "出力 0 件"), encoding="utf-8")
    assert la.main([str(p)]) == 0
    assert la.main([str(tmp_path / "none.md")]) == 2


def test_quote_only_is_flagged():
    t = "| 項目 | 主張 | エビデンス |\n|---|---|---|\n| S-1 | a | ```x``` |\n\n## 確かめられなかったこと\n"
    assert "quote-only" in by_id(t)[1] or "unverifiable" in by_id(t)[1]
