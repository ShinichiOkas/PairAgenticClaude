"""要求の網羅性検査 の武器（number_items.py / trace_coverage.py）のテスト。"""
import importlib.util
import sys
from pathlib import Path

sys.dont_write_bytecode = True
D = Path(__file__).resolve().parents[2] / "skills" / "scripts" / "要求の網羅性検査"


def load(name):
    spec = importlib.util.spec_from_file_location(name, D / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


ni = load("number_items")
tc = load("trace_coverage")

REQ = """# 要望
ログはこんな感じで出してほしい。結果が出るようにしてくれ。
- 重複は取り除く
- 速度は気にしない
"""


def test_numbering_and_ambiguity():
    rows = ni.number(REQ)
    assert [r[0] for r in rows] == ["R1", "R2", "R3", "R4"]
    assert "こんな感じ" in rows[0][2]
    assert "結果が出る" in rows[1][2]
    assert rows[2][2] == [] and rows[3][2] == []
    assert "[曖昧語: こんな感じ]" in ni.render(rows)


def test_numbering_deterministic_and_prefix():
    assert ni.render(ni.number(REQ, "Y")) == ni.render(ni.number(REQ, "Y"))
    assert ni.number(REQ, "Y")[0][0] == "Y1"


def test_number_cli_no_overwrite(tmp_path):
    src = tmp_path / "r.txt"
    src.write_text(REQ, encoding="utf-8")
    out = tmp_path / "i.txt"
    assert ni.main([str(src), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8").startswith("R1:")
    assert ni.main([str(src), "--out", str(out)]) == 2


ITEMS = ni.render(ni.number(REQ))

GOOD_OUT = """\
- ログを出力する [由来: R1]
- 結果を標準出力に出す [発明: R2 出力先は言われていない]
- 重複を除去する [由来: R3]
- 速度要件は設けない [扱い: スコープ外 R4]
"""


def test_trace_reports_invention_hole():
    res = tc.trace(tc.read_items(ITEMS), GOOD_OUT)
    assert res["only_invented"] == ["R2"]
    assert res["dropped"] == []
    assert len(res["invented"]) == 1


def test_dropped_and_untagged_and_bad_refs():
    out = "- ログを出力する [由来: R1]\n- 勝手な追加\n- 変な参照 [由来: R9]\n- 型違い [扱い: 保留 R4]\n"
    res = tc.trace(tc.read_items(ITEMS), out)
    assert set(res["dropped"]) == {"R2", "R3", "R4"}
    assert res["untagged"] == [2]
    p = "\n".join(res["problems"])
    assert "存在しない番号" in p and "扱いの型が不明" in p


def test_report_contradiction_detected():
    res = tc.trace(tc.read_items(ITEMS), GOOD_OUT)
    report = "- 事後条件「自分で定義を選んでいない」 ✅\n- 申告: 出力先は自分の解釈で決めた\n"
    f = tc.check_report(report, res)
    assert any("発明が 1 件" in x for x in f)
    assert any("自己申告" in x for x in f)


def test_report_without_invention_is_clean():
    out = "- a [由来: R1, R2]\n- b [由来: R3]\n- c [扱い: 延期 R4]\n"
    res = tc.trace(tc.read_items(ITEMS), out)
    assert res["dropped"] == [] and res["invented"] == []
    assert tc.check_report("- 自分で定義を選んでいない ✅\n", res) == []


def test_report_claims_all_covered_but_gap():
    res = tc.trace(tc.read_items(ITEMS), "- a [由来: R1]\n")
    assert any("写されていない" in x for x in tc.check_report("- 漏れなし ✅\n", res))


def test_cli(tmp_path, capsys):
    i, o, r = tmp_path / "i.txt", tmp_path / "o.md", tmp_path / "r.md"
    i.write_text(ITEMS, encoding="utf-8")
    o.write_text(GOOD_OUT, encoding="utf-8")
    r.write_text("自分で定義を選んでいない ✅\n", encoding="utf-8")
    assert tc.main([str(i), str(o)]) == 0
    assert tc.main([str(i), str(o), "--report", str(r), "--strict"]) == 1
    assert "発明で埋めた穴" in capsys.readouterr().out
    assert tc.main([str(i), str(tmp_path / "none")]) == 2
    bad = tmp_path / "bad.txt"
    bad.write_text("項目なし\n", encoding="utf-8")
    assert tc.main([str(bad), str(o)]) == 2
