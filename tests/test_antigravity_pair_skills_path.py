"""Antigravity 側のペア固有 Skill の置き場が、スクリプトと文書で 1 種類だけであることを確かめる。

正は install が配る ~/.gemini/config/pair-agent/skills/（home-claude/CLAUDE.md の「学習データの場所」と同じ）。
"""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANON = ".gemini/config/pair-agent/skills"
# ~/.gemini/.../pair-agent/skills を、\ と / の両方・%USERPROFILE%・~ ・$HOME を問わず拾う
PAT = re.compile(r"\.gemini[\/]+((?:[\w.-]+[\/]+)*?)pair-agent[\/]+skills(?![\w-])")


def tracked_text_files():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True).stdout
    for rel in out.decode("utf-8").split("\0"):
        if not rel or rel.startswith((".agents/", ".claude/", "docs/bugs/", "tests/")):
            continue
        if rel.startswith("home-claude/.agents/") or rel.startswith("home-claude/.claude/"):
            continue
        p = ROOT / rel
        if p.suffix in (".md", ".bat", ".sh", ".py", ".json") and p.is_file():
            yield rel, p.read_text(encoding="utf-8", errors="ignore")


def test_antigravity_pair_skills_path_is_single():
    found = {}
    for rel, text in tracked_text_files():
        for m in PAT.finditer(text):
            found.setdefault(m.group(0).replace("\\", "/"), []).append(rel)
    assert found, "Antigravity のペア Skill の置き場がどこにも書かれていない"
    assert set(found) == {CANON}, f"置き場が割れている: {found}"


def test_skillimport_and_docs_use_install_location():
    bat = (ROOT / "skillimport.bat").read_text(encoding="utf-8")
    assert r".gemini\config\pair-agent\skills" in bat
    install = (ROOT / "install.bat").read_text(encoding="utf-8")
    assert r".gemini\config" in install and r"pair-agent\skills" in install
    assert (ROOT / "home-claude/CLAUDE.md").read_text(encoding="utf-8") == (ROOT / "home-claude/GEMINI.md").read_text(encoding="utf-8")
