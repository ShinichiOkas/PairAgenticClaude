"""Skill 専用スクリプト（武器）の配布の仕組みのテスト。

emit_claude / emit_agents が `skills/scripts/<名前>/` を `<dest>/skills/<名前>/scripts/` に写し
SKILL.md に「武器」節を足すこと、無い Skill は従来どおりであること、
check_skills が孤児ディレクトリと docstring 欠落を拾うことを、一時ディレクトリで確かめる。
"""
import shutil
import sys
from pathlib import Path

import pytest

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import check_skills  # noqa: E402
import emit_agents  # noqa: E402
import emit_claude  # noqa: E402

TASKS = """\
design_acceptance_tests  : 武器技法, 無印技法
build                    : 無印技法
run_regression           : （機械）
execute_acceptance_tests : 無印技法
"""
SKILL = "---\ncapability: テスト\ntype: 技法\nmaturity: draft\n---\n{claim}\n\n本文\n"
SCRIPT = '"""数を数える決定性スクリプト。\n\n詳細な説明。\n"""\nprint("hi")\n'


@pytest.fixture
def world(tmp_path, monkeypatch):
    skills = tmp_path / "skills"
    (skills / "scripts" / "武器技法").mkdir(parents=True)
    (skills / "武器技法.md").write_text(SKILL.format(claim="武器のある技法。"), encoding="utf-8")
    (skills / "無印技法.md").write_text(SKILL.format(claim="素の技法。"), encoding="utf-8")
    (skills / "scripts" / "武器技法" / "count.py").write_text(SCRIPT, encoding="utf-8")
    (skills / "scripts" / "武器技法" / "data.txt").write_text("a\n", encoding="utf-8")
    (skills / "scripts" / "武器技法" / "__pycache__").mkdir()
    (skills / "scripts" / "武器技法" / "__pycache__" / "x.pyc").write_bytes(b"\0\1")
    models = tmp_path / "models"
    models.mkdir()
    mk = models / "m.mk"
    shutil.copy(REPO / "models" / "pair-agent-xs.mk", mk)
    mk.with_suffix(".tasks").write_text(TASKS, encoding="utf-8")
    monkeypatch.setattr(emit_claude, "SKILL_DIR", skills)
    monkeypatch.setattr(emit_claude, "SLUG_MAP", skills / "slugs.map")
    return tmp_path


def make_emit(world):
    return emit_claude.Emit(world / "models" / "m.mk", world / "models" / "m.tasks")


def test_script_copied_and_weapon_section_added(world):
    files = make_emit(world).skill_files(["武器技法"])
    assert set(files) == {"武器技法/SKILL.md", "武器技法/scripts/count.py",
                          "武器技法/scripts/data.txt"}
    assert files["武器技法/scripts/count.py"] == SCRIPT
    md = files["武器技法/SKILL.md"]
    assert "## 武器（スクリプト）" in md
    assert "`scripts/count.py` — 数を数える決定性スクリプト。" in md
    assert "python scripts/count.py --help" in md
    assert "data.txt" not in md  # .py だけが武器節に載る
    assert md.rstrip().endswith("--help`")  # 末尾に足される


def test_skill_without_scripts_unchanged(world):
    e = make_emit(world)
    files = e.skill_files(["無印技法"])
    assert list(files) == ["無印技法/SKILL.md"]
    assert "武器" not in files["無印技法/SKILL.md"]
    # 武器を持つ Skill が隣にあっても、無印の出力は同一
    both = e.skill_files(["武器技法", "無印技法"])
    assert both["無印技法/SKILL.md"] == files["無印技法/SKILL.md"]


def test_emit_claude_main_writes_scripts(world, monkeypatch, capsys):
    dest = world / "out"
    monkeypatch.setattr(sys, "argv", ["emit_claude.py", str(world / "models" / "m.mk"),
                                      "--dest=" + str(dest)])
    assert emit_claude.main() == 0
    assert (dest / "skills" / "武器技法" / "scripts" / "count.py").read_text(
        encoding="utf-8") == SCRIPT
    assert not (dest / "skills" / "武器技法" / "scripts" / "__pycache__").exists()
    assert (dest / "skills" / "無印技法" / "SKILL.md").exists()
    assert not (dest / "skills" / "無印技法" / "scripts").exists()
    assert "skill 2" in capsys.readouterr().out  # スクリプトを skill に数えない


def test_emit_agents_copies_to_both_platforms(world, monkeypatch):
    dest = world / "out2"
    monkeypatch.setattr(sys, "argv", ["emit_agents.py", str(world / "models" / "m.mk"),
                                      "--dest=" + str(dest), "--target=all"])
    assert emit_agents.main() == 0
    for base in (dest / ".claude", dest / ".agents"):
        assert (base / "skills" / "武器技法" / "scripts" / "count.py").exists()
        assert "## 武器（スクリプト）" in (base / "skills" / "武器技法" / "SKILL.md").read_text(
            encoding="utf-8")


def test_check_weapons_ok(world):
    skills = world / "skills"
    assert check_skills.check_weapons(skills) == []


def test_check_weapons_orphan_and_missing_docstring(world):
    skills = world / "skills"
    (skills / "scripts" / "存在しない技法").mkdir()
    (skills / "scripts" / "存在しない技法" / "a.py").write_text('"""ある。"""\n', encoding="utf-8")
    (skills / "scripts" / "武器技法" / "nodoc.py").write_text("print(1)\n", encoding="utf-8")
    (skills / "scripts" / "武器技法" / "bad.py").write_text("def (:\n", encoding="utf-8")
    (skills / "scripts" / "stray.py").write_text('"""x"""\n', encoding="utf-8")
    probs = check_skills.check_weapons(skills)
    text = "\n".join(probs)
    assert "武器の孤児" in text and "存在しない技法" in text
    assert "nodoc.py" in text and "docstring" in text
    assert "bad.py" in text and "解析できない" in text
    assert "stray.py" in text
    assert len(probs) == 4


def test_check_weapons_home_claude(world):
    home = world / "home-skills"
    (home / "proc" / "scripts").mkdir(parents=True)
    (home / "proc" / "SKILL.md").write_text("---\nname: proc\n---\n", encoding="utf-8")
    (home / "proc" / "scripts" / "ok.py").write_text('"""ok"""\n', encoding="utf-8")
    (home / "proc" / "scripts" / "nodoc.py").write_text("x = 1\n", encoding="utf-8")
    (home / "noskill" / "scripts").mkdir(parents=True)
    probs = check_skills.check_weapons(world / "skills", home)
    text = "\n".join(probs)
    assert "proc/scripts/nodoc.py" in text
    assert "noskill/scripts/" in text and "`SKILL.md` が無い" in text
    assert "ok.py" not in text
