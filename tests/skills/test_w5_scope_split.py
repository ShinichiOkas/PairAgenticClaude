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


ss = load("保証範囲の切り出し", "scope_split")

SPEC = """# 仕様
- S-1 遅い判定は 1000ms 以上
- S-2 標準ライブラリのみを使う
- S-3 層構造に違反しない
- S-4 縮退はログを出す
"""

ASSURANCE = """# 設計保証
| 項目 | 主張 | エビデンス |
|---|---|---|
| S-2 | 標準のみ | 出力 0 件 |
| S-3 | 層を守る | 出力 0 件 |

## 保証しなかったこと
- S-4 起こせないため保証できなかった
"""


def test_clean_split():
    r = ss.split(SPEC, ASSURANCE, ["S-1"])
    assert (r["guaranteed"], r["residual"], r["external_only"]) == (["S-2", "S-3"], ["S-4"], ["S-1"])
    assert r["errors"] == 0


def test_excess_is_flagged():
    r = ss.split(SPEC, ASSURANCE.replace("## 保証しなかったこと", "| S-9 | 余計 | 出力 |\n\n## 保証しなかったこと"), ["S-1"])
    assert r["excess"] == ["S-9"] and r["errors"] == 1


def test_external_item_in_assurance_is_error():
    r = ss.split(SPEC, ASSURANCE.replace("| S-3 |", "| S-1 |"), ["S-1"])
    assert r["external_guaranteed"] == ["S-1"]
    assert "S-3" in r["uncovered"]


def test_uncovered_when_neither_guaranteed_nor_residual_nor_external():
    r = ss.split(SPEC, ASSURANCE.replace("- S-4 起こせないため保証できなかった", ""), ["S-1"])
    assert r["uncovered"] == ["S-4"]


def test_residual_id_outside_residual_section_counts_as_guarantee():
    r = ss.split(SPEC, "| S-4 | x | y |\n", ["S-1", "S-2", "S-3"])
    assert r["guaranteed"] == ["S-4"]


def test_unknown_external_id_is_error():
    assert ss.split(SPEC, ASSURANCE, ["S-1", "S-77"])["unknown_external"] == ["S-77"]


def test_custom_id_pattern():
    spec = "- R1: a\n- R2: b\n"
    r = ss.split(spec, "| R1 | x | y |\n", [], r"R\d+")
    assert r["spec_items"] == ["R1", "R2"] and r["uncovered"] == ["R2"]


def test_cli_exit_codes(tmp_path):
    s, a = tmp_path / "s.md", tmp_path / "a.md"
    s.write_text(SPEC, encoding="utf-8")
    a.write_text(ASSURANCE, encoding="utf-8")
    assert ss.main(["--spec", str(s), "--assurance", str(a), "--external", "S-1"]) == 0
    assert ss.main(["--spec", str(s), "--assurance", str(a)]) == 1  # S-1 が未カバー
    assert ss.main(["--spec", str(tmp_path / "x"), "--assurance", str(a)]) == 2
    s.write_text("本文だけ", encoding="utf-8")
    assert ss.main(["--spec", str(s), "--assurance", str(a)]) == 2
