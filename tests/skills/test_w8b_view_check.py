"""三つの基本ビュー / view_check.py のテスト。"""
import json

from _w8b_load import check_locator, check_read_only, graph, load, run

m = load("三つの基本ビュー", "view_check")


def build(tmp_path):
    g = graph(tmp_path)
    heat, ctl = g.add("component", "加熱"), g.add("component", "制御")
    mcu = g.add("part", "マイコン")
    g.link("allocates", ctl, mcu)
    lg = g.add("model", "論理の図", {"viewpoint": "logical"})
    g.link("shows", lg, heat)
    g.link("shows", lg, ctl)
    return g


def test_no_model_means_nothing_is_shown_yet(tmp_path, capsys):
    g = graph(tmp_path)
    g.add("component", "加熱")
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "モデル（1 枚の図）が 1 枚も無い" in out
    assert "| 論理ビュー | （なし）⚠ |" in out and "## 検出\n- なし" in out


def test_missing_views_and_unviewed_elements(tmp_path, capsys):
    g = build(tmp_path)
    g.add("component", "表示")
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1 and "| 論理ビュー | MO1 論理の図（component×2） |" in out and "| 実装ビュー | （なし）⚠ |" in out
    assert "[view_missing:view:implementation]" in out and "[view_missing:view:allocation]" in out
    assert "[no_view:LC3]" in out and "no_view:PT1" not in out  # 実装ビューが無いうちは部品を問わない
    assert "- LC3 表示（載るべきビュー: 論理ビュー）" in out and "- PT1 マイコン（載るべきビュー: 実装ビュー）" in out
    code, out, _ = run(m, capsys, "--db", g.path, "--json")
    data = json.loads(out)
    assert data["missing"] == ["implementation", "allocation"] and data["unviewed"] == ["LC3"]
    assert {f["rule"] for f in data["findings"]} == {"view_missing", "no_view"}  # orphan などは出さない


def test_three_views_and_mixed_kinds(tmp_path, capsys):
    g = build(tmp_path)
    im = g.add("model", "実装の図", {"viewpoint": "実装"})
    g.link("shows", im, "PT1")
    g.link("shows", im, "LC1")  # 実装の図に論理コンポーネントが混ざる
    al = g.add("model", "割り付けの図", {"viewpoint": "allocation"})
    g.link("shows", al, "LC2")
    g.link("shows", al, "PT1")
    other = g.add("model", "課題ビュー", {"viewpoint": "課題 IS1"})
    g.add("model", "視点なし")
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 1 and "MO2 実装の図（component×1・part×1）⚠種類が混ざる" in out
    assert "MO3 割り付けの図（component×1・part×1）" in out and "[mixed_kinds:MO3]" not in out
    assert "[mixed_kinds:MO2]" in out and "view_missing" not in out
    assert f"- [課題 IS1] {other} 課題ビュー" in out and "視点（attrs.viewpoint）の無いモデル" in out
    g.update(im, attrs={"whiteboard": True})
    code, out, _ = run(m, capsys, "--db", g.path)
    assert code == 0 and "（ホワイトボード）" in out


def test_locator_and_read_only(tmp_path, capsys, monkeypatch):
    g = build(tmp_path)
    check_read_only(m, tmp_path, capsys, g.path)
    check_locator(m, tmp_path, capsys, monkeypatch, g.path)
