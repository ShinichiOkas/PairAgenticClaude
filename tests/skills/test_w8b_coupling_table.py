"""括りと結合上限 / coupling_table.py のテスト。数は表にするだけで、検出は宣言した上限の超過だけ。"""
import json

from _w8b_load import check_locator, check_read_only, graph, load, run

m = load("括りと結合上限", "coupling_table")


def build(tmp_path, limit=None):
    g = graph(tmp_path)
    attrs = {} if limit is None else {"max_coupling": limit}
    grp = g.add("component", "炊飯", attrs)
    kids = [g.add("component", t, parent=grp) for t in ("保持", "加熱", "制御")]
    outs = [g.add("component", t) for t in ("表示", "電源")]
    g.link("relation", kids[2], kids[1], predicate="通電を指示する")
    g.link("relation", kids[1], outs[1], predicate="電力を受ける")
    g.link("relation", kids[2], outs[0], predicate="状態を知らせる")
    return g


def test_counts_are_a_table_and_never_a_finding_without_a_limit(tmp_path, capsys):
    g = graph(tmp_path)
    lcs = [g.add("component", f"要素 {i}") for i in range(8)]
    for i, a in enumerate(lcs):
        for b in lcs[i + 1:]:
            g.link("relation", a, b, predicate="知らせる")  # 全部つながっている（28 の結合）
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "要素間の結合 28（最大 n(n-1)/2 = 28）" in out and "√n ≈ 2.83" in out
    assert "数が大きいこと自体は課題にしない" in out and "## 検出\n- なし" in out


def test_group_row_and_declared_limit(tmp_path, capsys):
    g = build(tmp_path)
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "| LC1 炊飯 | 3 | 3 | 1 | 2 | — |" in out
    g.update("LC1", attrs={"max_coupling": 1})
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1 and "| 1 ⚠超過 |" in out and "[coupling_over:LC1]" in out and "宣言した上限 1" in out
    code, out, _ = run(m, capsys, "--db", g.path, "--json")
    data = json.loads(out)
    assert code == 1 and data["groups"][0]["over"] is True and {f["rule"] for f in data["findings"]} == {"coupling_over"}
    g.update("LC1", attrs={"max_coupling": 2})
    assert run(m, capsys, "--db", g.path)[0] == 0  # 上限ちょうどは超過ではない


def test_root_compares_candidate_structures(tmp_path, capsys):
    g = graph(tmp_path)
    d = g.add("decision_point", "分け方")
    a = g.add("option", "3 つに分ける", parent=d)
    b = g.add("option", "分解しない", parent=d)
    xs = [g.add("component", f"A{i}", parent=a) for i in range(3)]
    g.add("component", "まるごと", parent=b)
    g.link("relation", xs[0], xs[1], predicate="渡す")
    g.link("relation", xs[1], xs[2], predicate="渡す")
    code, out, _ = run(m, capsys, "--db", g.path, "--root", a, "--root", b, "--root", xs[0])
    assert code == 0
    assert "| D1-A 3 つに分ける | 3 | 3 | 2 | 0 | — |" in out and "| D1-B 分解しない | 1 | 1 | 0 | 0 | — |" in out
    assert "LC1 は括りではない" in out
    code, _, err = run(m, capsys, "--db", g.path, "--root", "LC99")
    assert code == 2 and "LC99" in err


def test_unreadable_limit_is_reported(tmp_path, capsys):
    g = build(tmp_path, limit="少なめ")
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1 and "読めない（'少なめ'）" in out and "0 以上の整数でない" in out


def test_locator_and_read_only(tmp_path, capsys, monkeypatch):
    g = build(tmp_path)
    check_read_only(m, tmp_path, capsys, g.path)
    check_locator(m, tmp_path, capsys, monkeypatch, g.path)
