"""ATAM / atam_discards.py のテスト。決めたことではなく、捨てたことを並べる。"""
import json

from _w8b_load import check_locator, check_read_only, graph, load, run

m = load("ATAM", "atam_discards")


def build(tmp_path, cons=True):
    g = graph(tmp_path)
    sh = g.add("stakeholder", "利用者")
    cns = [g.add("concern", t, {"weight": 5}) for t in ("待ち時間", "美味しさ")]
    is_ = g.add("issue", "甘みと時間")
    for c in cns:
        g.link("source", c, sh)
        g.link("affects", is_, c)
    d = g.add("decision_point", "昇温の方式")
    g.link("anchors", d, is_)
    a_cons = [{"text": "時間が延びる", "origin": "essential", "measure": "+10 分"}] if cons else []
    a = g.add("option", "昇温曲線の設計", {"viewpoint": "制御", "cons": a_cons}, parent=d)
    g.add("option", "加圧で高速化", {"viewpoint": "構造", "cons": [{"text": "部品が増える", "origin": "means"}]}, parent=d)
    g.add("option", "事前浸水", {"viewpoint": "利用者", "cons": ["手間"]}, parent=d)
    d2 = g.add("decision_point", "保温")
    k = g.add("option", "常時保温", {"cons": [{"text": "待機電力", "origin": "means"}]}, parent=d2)
    g.add("option", "保温しない", parent=d2)
    g.link("conflicts", a, k)
    g.add("decision_point", "未決のまま")
    g.actor = "human"
    g.decide(d, a, conditions=["家庭用 100V"])
    g.decide(d2, k)
    return g


def test_discards_per_decision(tmp_path, capsys):
    g = build(tmp_path)
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0
    assert "## D1 昇温の方式 → 採用 D1-A 昇温曲線の設計" in out
    assert "- 関わる関心事: CN1 待ち時間, CN2 美味しさ（2 つ以上: トレードオフ点の候補）" in out
    assert "- 採用した案の代償: 時間が延びる（本質的・+10 分）" in out
    assert "- 捨てた案: D1-B 加圧で高速化（視点: 構造） [却下] —— 欠点: 部品が増える（手段由来）" in out
    assert "- 捨てた案: D1-C 事前浸水（視点: 利用者） [却下] —— 欠点: 手間（由来なし）" in out
    assert "- 案どうしの衝突（" in out and "D2-A 常時保温 [採用]" in out
    assert "D3" not in out  # 未決の決定点は、まだ何も捨てていない
    data = json.loads(run(m, capsys, "--db", g.path, "--json")[1])
    assert [r["dp"] for r in data["decisions"]] == ["D1", "D2"]
    assert data["decisions"][0]["candidate_tradeoff_point"] is True and data["decisions"][1]["candidate_tradeoff_point"] is False


def test_adopted_option_without_cons_is_a_finding(tmp_path, capsys):
    g = build(tmp_path, cons=False)
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1 and "- 採用した案の代償: ⚠ 書かれていない" in out and "[no_cons:D1-A]" in out
    code, out, _ = run(m, capsys, "--db", g.path, "--dp", "D2")
    assert code == 0 and "D1 昇温" not in out and "no_cons" not in out


def test_no_decisions(tmp_path, capsys):
    g = graph(tmp_path)
    g.add("decision_point", "まだ")
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "決断がまだ無い" in out


def test_locator_and_read_only(tmp_path, capsys, monkeypatch):
    g = build(tmp_path)
    check_read_only(m, tmp_path, capsys, g.path)
    check_locator(m, tmp_path, capsys, monkeypatch, g.path)
