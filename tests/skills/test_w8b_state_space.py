"""状態の三段導出 / state_space.py のテスト。"""
import json

from _w8b_load import check_locator, check_read_only, graph, load, run

m = load("状態の三段導出", "state_space")


def build(tmp_path):
    """炊飯器（§12.5）: 保持・加熱・制御の 3 部品 × 2 状態 = 8 通り。"""
    g = graph(tmp_path)
    hold, heat, ctl = g.add("component", "保持"), g.add("component", "加熱"), g.add("component", "制御")
    s = {n: g.add("component_state", n, parent=p) for n, p in
         (("空", hold), ("保持中", hold), ("停止", heat), ("通電中", heat), ("待機", ctl), ("実行中", ctl))}
    g.add("system_state", "待機", {"of": [s["停止"], s["待機"]]})
    g.add("system_state", "炊飯中", {"of": [s["保持中"], s["通電中"], s["実行中"]]})
    g.add("system_state", "空焚き", {"of": [s["空"], s["通電中"]], "forbidden": True, "reason": "空焚きになる"})
    return g, s


def test_gaps_dont_care_and_table(tmp_path, capsys):
    g, s = build(tmp_path)
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1
    assert "- LC1 保持: CS1 空・CS2 保持中" in out and "- 直積 8 通り" in out
    assert "| SS1 待機 | CS3 ∧ CS5 |  | LC1 |  |  |" in out and "| SS3 空焚き | CS1 ∧ CS4 | 禁止（空焚きになる） |" in out
    assert "網羅漏れ 3 通り" in out and "  - CS1 空 ∧ CS3 停止 ∧ CS6 実行中" in out
    assert "[state_gap:system_state]" in out and "[state_dont_care:SS1]（情報）" in out
    code, out, _ = run(m, capsys, "--db", g.path, "--json")
    data = json.loads(out)
    assert code == 1 and len(data["gaps"]) == 3 and data["titles"]["CS1"] == "空"
    assert {f["rule"] for f in data["findings"]} == {"state_gap", "state_dont_care"}


def test_show_limits_the_listed_combos(tmp_path, capsys):
    g, _ = build(tmp_path)
    code, out, _ = run(m, capsys, "--db", g.path, "--show", "1")
    assert code == 1 and "…ほか 2 通り" in out


def test_overlap_and_undefined(tmp_path, capsys):
    g, s = build(tmp_path)
    g.add("system_state", "保温", {"of": [s["保持中"], s["通電中"]]})
    g.add("system_state", "矛盾", {"of": [s["空"], s["保持中"]]})
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1 and "重複 1 通り" in out and "← SS2・SS4" in out
    assert "[state_overlap:system_state]" in out and "[state_undefined:SS5]" in out and "2 つ指している" in out


def test_complete_definition_leaves_only_info(tmp_path, capsys):
    g, s = build(tmp_path)
    g.add("system_state", "準備中", {"of": [s["停止"], s["実行中"]]})
    g.add("system_state", "保温", {"of": [s["保持中"], s["通電中"], s["待機"]]})
    is_ = g.add("issue", "待機・準備中のとき保持はどちらでもよいか（待機電力が決める）")
    g.link("about", is_, "SS1")
    g.link("about", is_, "SS4")
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "網羅漏れ" not in out and "| SS1 待機 | CS3 ∧ CS5 |  | LC1 | IS1 |  |" in out
    assert "## 検出\n- なし" in out


def test_world_flow(tmp_path, capsys):
    g = graph(tmp_path)
    w = [g.add("world_state", t, a) for t, a in (("米と水がある", {"mark": "初めの状態"}), ("炊いている", {}),
                                                  ("取り出した", {"mark": "goal"}), ("孤立", {}))]
    g.link("transitions", w[0], w[1])
    g.link("transitions", w[1], w[2])
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1 and "第 1 段: 世界の状態: 状態 4・遷移 2・初めの状態 WS1" in out
    assert "  - WS4 孤立: 供給元なし・行き止まり" in out and "[state_flow:WS4]" in out
    assert "まだ無い（attrs.of=[CS…]" in out


def test_locator_and_read_only(tmp_path, capsys, monkeypatch):
    g, _ = build(tmp_path)
    check_read_only(m, tmp_path, capsys, g.path)
    check_locator(m, tmp_path, capsys, monkeypatch, g.path)
