import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _w4_load import load

m = load("文書ごとの正の向き", "check_direction.py")


def test_kinds():
    assert m.check_text("# t\n> 正の向き: 実装が正\n")["declared"] == "実装が正"
    assert m.check_text("正の向き：文書が正\n実装の担い手: 山田\n") == {"declared": "文書が正", "problems": []}
    r = m.check_text("正の向き: 文書が正\n")
    assert r["problems"] == ["文書が正なのに「実装の担い手:」が無い"]
    assert m.check_text("正の向き: 両方が正\n")["declared"] == "両方"
    assert m.check_text("本文だけ\n")["declared"] is None


def test_generated_requires_command_and_noedit():
    assert len(m.check_text("正の向き: 生成物\n")["problems"]) == 2
    ok = "正の向き: 生成物\n生成コマンド: python gen.py\n手で編集しない\n"
    assert m.check_text(ok)["problems"] == []


def test_declaration_beyond_head_is_missed():
    text = "\n" * 40 + "正の向き: 実装が正\n"
    assert m.check_text(text)["declared"] is None


def test_scaffold_passes_own_check():
    for kind, block in m.SCAFFOLDS.items():
        filled = block.replace("<誰が実装を直すか>", "A").replace("<元から生成するコマンド>", "make")
        assert m.check_text(filled)["problems"] == [], kind


def test_cli(tmp_path):
    (tmp_path / "ok.md").write_text("正の向き: 実装が正\n", encoding="utf-8")
    assert m.main(["check", str(tmp_path)]) == 0
    (tmp_path / "ng.md").write_text("なし\n", encoding="utf-8")
    assert m.main(["check", str(tmp_path)]) == 1
    assert m.main(["scaffold", "--kind", "生成物"]) == 0
