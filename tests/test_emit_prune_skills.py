"""`--prune` が skill（出力先の skills/<名>/）にも効くことのテスト。すべて一時ディレクトリ。

- 今回の書き出しに無い生成物（SKILL.md に自動生成の印）は消える（scripts/ ごと）
- 印の無いもの（手で置いた）は残り、「?」で出る
- dry-run では消えない
- emit_claude / emit_agents の main を通しても同じ
"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
import emit_agents  # noqa: E402  # pyright: ignore[reportMissingImports]
import emit_claude  # noqa: E402  # pyright: ignore[reportMissingImports]

MARKED = "---\nname: x\n---\n\n<!-- 自動生成。手で編集しない。正は skills/x.md -->\n"


def make(root: Path) -> Path:
    s = root / "skills"
    (s / "古い生成物" / "scripts").mkdir(parents=True)
    (s / "古い生成物" / "SKILL.md").write_text(MARKED, encoding="utf-8")
    (s / "古い生成物" / "scripts" / "a.py").write_text("print(1)\n", encoding="utf-8")
    (s / "手置き").mkdir()
    (s / "手置き" / "SKILL.md").write_text("---\nname: h\n---\n本文\n", encoding="utf-8")
    (s / "今回分").mkdir()
    (s / "今回分" / "SKILL.md").write_text(MARKED, encoding="utf-8")
    return s


def test_prune_removes_only_marked_and_not_kept(tmp_path):
    s = make(tmp_path)
    rows = emit_claude.prune_skills(s, {"今回分"}, prune=True, dry=False)
    assert {(m, p.name) for m, p in rows} == {("−", "古い生成物"), ("?", "手置き")}
    assert not (s / "古い生成物").exists()
    assert (s / "手置き" / "SKILL.md").exists()
    assert (s / "今回分" / "SKILL.md").exists()


def test_dry_run_and_no_prune_keep_everything(tmp_path):
    s = make(tmp_path)
    for prune, dry in ((True, True), (False, False)):
        rows = emit_claude.prune_skills(s, {"今回分"}, prune=prune, dry=dry)
        assert {(m, p.name) for m, p in rows} == {("・", "古い生成物"), ("?", "手置き")}
        assert (s / "古い生成物" / "scripts" / "a.py").exists()


def test_emit_claude_main_prune(tmp_path, monkeypatch):
    s = make(tmp_path)
    mk = str(REPO / "models" / "devops.mk")
    monkeypatch.setattr(sys, "argv", ["emit_claude.py", mk, "--dest=" + str(tmp_path), "--dry-run", "--prune"])
    assert emit_claude.main() == 0
    assert (s / "古い生成物").exists()
    monkeypatch.setattr(sys, "argv", ["emit_claude.py", mk, "--dest=" + str(tmp_path), "--prune"])
    assert emit_claude.main() == 0
    assert not (s / "古い生成物").exists()
    assert (s / "手置き").exists()


def test_emit_agents_main_prune_both_targets(tmp_path, monkeypatch):
    c = make(tmp_path / ".claude")
    g = make(tmp_path / ".agents")
    mk = str(REPO / "models" / "devops.mk")
    base = ["emit_agents.py", mk, "--target=all", "--dest=" + str(tmp_path)]
    monkeypatch.setattr(sys, "argv", base + ["--dry-run", "--prune"])
    assert emit_agents.main() == 0
    assert (c / "古い生成物").exists() and (g / "古い生成物").exists()
    monkeypatch.setattr(sys, "argv", base + ["--prune"])
    assert emit_agents.main() == 0
    for d in (c, g):
        assert not (d / "古い生成物").exists()
        assert (d / "手置き").exists()
