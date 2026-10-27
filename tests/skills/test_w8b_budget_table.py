"""区間目標の予算配分 / budget_table.py のテスト。"""
import json

from _w8b_load import check_locator, check_read_only, graph, load, run

m = load("区間目標の予算配分", "budget_table")


def build(tmp_path, budgets=(30, 15, 10, 15)):
    g = graph(tmp_path)
    qs = g.add("qas", "炊飯の区間", {"target": 60, "unit": "分"})
    for t, b in zip(("浸水", "昇温", "沸騰の維持", "蒸らし"), budgets):
        g.link("allocates", qs, g.add("component", t), attrs={"budget": b, "basis": "知見（仮説）"})
    g.add("requirement", "関係の無い要求")  # 予算表に出ない
    return g


def test_over_budget_is_a_finding_and_the_table_shows_the_sum(tmp_path, capsys):
    g = build(tmp_path)
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1
    assert "## QS1 炊飯の区間 [仮説]  目標 60 分" in out and "| LC1 浸水 | 30 分 | 仮説 | 知見（仮説） |" in out
    assert "合計 70 分 ／ 目標 60 分 → 超過 10 分" in out and "[budget_over:QS1]" in out
    code, out, _ = run(m, capsys, "--db", g.path, "--json")
    data = json.loads(out)
    assert code == 1 and [t["id"] for t in data["tables"]] == ["QS1"]
    assert (data["tables"][0]["total"], data["tables"][0]["excess"]) == (70, 10)
    assert {f["rule"] for f in data["findings"]} == {"budget_over"}  # この Skill の規則だけ（unallocated などは出さない）


def test_within_budget_exits_zero_and_shows_the_remainder(tmp_path, capsys):
    g = build(tmp_path, budgets=(30, 15, 5, 10))
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "残り 0 分" in out and "## 検出\n- なし" in out


def test_unreadable_budgets_are_shown_not_summed(tmp_path, capsys):
    g = build(tmp_path, budgets=(30, "十分", 10, 15))
    lc = g.add("component", "表示")
    g.link("allocates", "QS1", lc, attrs={"budget": 2, "unit": "Wh"})
    g.link("allocates", "QS1", g.add("component", "予算なし"))
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1 and "数でない（合計に入れない）" in out and "単位が目標と違う（合計に入れない）" in out
    assert "予算なし（合計に入れない）" in out and "合計 55 分" in out and "budget_over" not in out
    assert out.count("[budget_unreadable:") == 2


def test_id_filter_and_no_table(tmp_path, capsys):
    g = build(tmp_path)
    g.add("qas", "保温の区間", {"target": 5})
    code, out, _ = run(m, capsys, "--db", g.path, "--id", "QS2")
    assert code == 0 and "QS2 保温の区間" in out and "QS1" not in out and "（配分なし）" in out
    empty = graph(tmp_path / "e")
    empty.add("requirement", "要求だけ")
    code, out, _ = run(m, capsys, "--db", empty.path)
    assert code == 0 and "予算表なし" in out


def test_locator_and_read_only(tmp_path, capsys, monkeypatch):
    g = build(tmp_path)
    check_read_only(m, tmp_path, capsys, g.path)
    check_locator(m, tmp_path, capsys, monkeypatch, g.path)
