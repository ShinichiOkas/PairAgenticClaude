"""トレードオフの明示 / tradeoff_lines.py のテスト。手段と代償を同じ行に書く。"""
import json

from _w8b_load import check_locator, check_read_only, graph, load, run

m = load("トレードオフの明示", "tradeoff_lines")


def build(tmp_path):
    g = graph(tmp_path)
    d = g.add("decision_point", "昇温の方式")
    a = g.add("option", "昇温曲線の設計", {"pros": ["甘み"], "cons": [
        {"text": "炊き上がりまでの時間が延びる", "origin": "essential", "measure": "+10 分", "owner": "制御設計"},
        "検証が試作後になる"]}, parent=d)
    b = g.add("option", "加圧で高速化", parent=d)
    d2 = g.add("decision_point", "保温")
    k = g.add("option", "常時保温", parent=d2)
    g.link("conflicts", a, k)
    g.link("synergy", a, b)
    g.actor = "human"
    g.decide(d, a)
    g.decide(d2, k)
    return g


def test_one_line_per_means_and_cost(tmp_path, capsys):
    g = build(tmp_path)
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1
    assert ("- D1: 「甘み」を得るために「炊き上がりまでの時間が延びる」を失う（手段: D1-A 昇温曲線の設計・由来: 本質的・"
            "定量: +10 分・引き受け: 制御設計）") in out
    assert "「検証が試作後になる」を失う（手段: D1-A 昇温曲線の設計・由来: 未記入・定量: 書いていない・引き受け: 書いていない）" in out
    assert "- D2: 「常時保温」を採るために …… ⚠ 代償が書かれていない" in out and "[no_cons:D2-A]" in out
    assert "D1-A 昇温曲線の設計 と D2-A 常時保温 [採用] は対立する" in out
    assert "D1-A 昇温曲線の設計 と D1-B 加圧で高速化 [却下] は相乗効果がある" in out
    assert out.count("は対立する") == 1  # 採用どうしの関係は 1 行
    data = json.loads(run(m, capsys, "--db", g.path, "--json")[1])
    assert [x["cost"] for x in data["lines"]] == ["炊き上がりまでの時間が延びる", "検証が試作後になる"]
    assert data["no_cons"] == [{"dp": "D2", "option": "D2-A", "means": "常時保温"}]
    assert {f["rule"] for f in data["findings"]} == {"no_cons"}


def test_dp_filter_and_clean_exit(tmp_path, capsys):
    g = build(tmp_path)
    code, out, _ = run(m, capsys, "--db", g.path, "--dp", "D1")
    assert code == 0 and "D2:" not in out and "## 検出\n- なし" in out
    g.update("D2-A", attrs={"cons": [{"text": "待機電力", "origin": "means"}]})
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "- D2: 「常時保温」を採るために「待機電力」を失う（手段: D2-A 常時保温・由来: 手段由来" in out


def test_no_adopted_options(tmp_path, capsys):
    g = graph(tmp_path)
    g.add("decision_point", "まだ")
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "- なし（採用した案がまだ無い）" in out


def test_locator_and_read_only(tmp_path, capsys, monkeypatch):
    g = build(tmp_path)
    check_read_only(m, tmp_path, capsys, g.path)
    check_locator(m, tmp_path, capsys, monkeypatch, g.path)
