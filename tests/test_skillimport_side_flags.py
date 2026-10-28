"""skillimport.bat の片側指定（--claude-only / --antigravity-only）を確かめる。

静的: usage・SKILL.md に載り、batch の両側の書き込みが指定で分岐している。
動的: 一時ディレクトリを USERPROFILE に見立てて実際に走らせる（本物の home には触れない）。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
BAT = ROOT / "skillimport.bat"
SKILL = ROOT / "home-claude" / "skills" / "skill-survey" / "SKILL.md"


def bat_text():
    return BAT.read_text(encoding="utf-8")


def test_flags_in_usage_and_skill_md():
    bat, md = bat_text(), SKILL.read_text(encoding="utf-8")
    for flag in ("--claude-only", "--antigravity-only"):
        assert flag in bat.split(":usage", 1)[1], f"usage に {flag} が無い"
        assert flag in md, f"SKILL.md に {flag} が無い"
    assert "片側だけ置き換えたいときは" in md and "必ず付ける" in md


def test_writes_branch_on_side_flags():
    bat = bat_text()
    for line in bat.splitlines():
        if "copy /y" in line or "mkdir" in line:
            continue
    # 各側の exist 判定は DO_C / DO_A で守られている
    assert 'if "%DO_C%"=="1" if exist "%CLAUDE_DST%' in bat
    assert 'if "%DO_A%"=="1" if exist "%ANTIGRAVITY_DST%' in bat
    assert 'if "%DO_C%"=="1" if not exist "%CLAUDE_DST%" mkdir' in bat
    assert 'if "%DO_A%"=="1" if not exist "%ANTIGRAVITY_DST%" mkdir' in bat
    # フラグの解析が DO_C / DO_A を落とす
    assert '--claude-only" set "DO_A=0"' in bat
    assert '--antigravity-only" set "DO_C=0"' in bat


def run_bat(home, *args):
    env = dict(os.environ, USERPROFILE=str(home))
    return subprocess.run(["cmd", "/c", str(BAT), *args], env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace", timeout=120, stdin=subprocess.DEVNULL)


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe 専用")
def test_antigravity_only_force_does_not_touch_claude(tmp_path):
    home = tmp_path / "home"
    cl = home / ".claude" / "pair-agent" / "skills"
    ag = home / ".gemini" / "config" / "pair-agent" / "skills"
    cl.mkdir(parents=True)
    ag.mkdir(parents=True)
    src = sorted((ROOT / "examples" / "skills").glob("*.md"))
    assert src
    name = src[0].name
    (cl / name).write_text("MINE-CLAUDE", encoding="utf-8")
    (ag / name).write_text("MINE-AG", encoding="utf-8")

    r = run_bat(home, "--antigravity-only", "--force")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (cl / name).read_text(encoding="utf-8") == "MINE-CLAUDE"
    assert (ag / name).read_text(encoding="utf-8") == src[0].read_text(encoding="utf-8")
    # Claude 側には他のファイルも作られない
    assert [p.name for p in cl.iterdir()] == [name]
    assert len(list(ag.iterdir())) == len(src)

    # 逆側
    (ag / name).write_text("MINE-AG", encoding="utf-8")
    r = run_bat(home, "--force", "--claude-only")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (ag / name).read_text(encoding="utf-8") == "MINE-AG"
    assert (cl / name).read_text(encoding="utf-8") == src[0].read_text(encoding="utf-8")


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe 専用")
def test_default_imports_both_and_protects_existing(tmp_path):
    home = tmp_path / "home"
    cl = home / ".claude" / "pair-agent" / "skills"
    cl.mkdir(parents=True)
    name = sorted((ROOT / "examples" / "skills").glob("*.md"))[0].name
    (cl / name).write_text("MINE", encoding="utf-8")
    r = run_bat(home)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (cl / name).read_text(encoding="utf-8") == "MINE"
    ag = home / ".gemini" / "config" / "pair-agent" / "skills"
    assert (ag / name).exists()


@pytest.mark.skipif(sys.platform != "win32", reason="cmd.exe 専用")
def test_list_with_side_writes_nothing(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    r = run_bat(home, "--list", "--antigravity-only")
    assert r.returncode == 0, r.stdout + r.stderr
    assert not (home / ".claude").exists() and not (home / ".gemini").exists()
