"""フックの配布: settings.json へ「足すだけ」の道具と、配る物の整合を確かめる。

守ること: 同じ項目は二重に足さない／ほかのキー（許可・鍵など）に触らない／壊れた JSON は書かずに止める／
雛形に鍵や PC 固有の値を入れない／インストーラがフックを ~/.claude/hooks へ写す。
"""
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT / "home-claude" / "settings-hooks.json"
HOOK = ROOT / "home-claude" / "hooks" / "agent_watch_reminder.py"

spec = importlib.util.spec_from_file_location("merge_claude_hooks", ROOT / "tools" / "merge_claude_hooks.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def run(settings: Path, *extra: str) -> int:
    return mod.main(["--settings", str(settings), "--template", str(TEMPLATE), *extra])


def read(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def count_hooks(d: dict) -> int:
    return sum(len(e["hooks"]) for e in d.get("hooks", {}).get("PostToolUse", []))


def test_creates_when_missing(tmp_path):
    s = tmp_path / "settings.json"
    assert run(s) == 0
    assert count_hooks(read(s)) == 1


def test_adds_without_touching_other_keys_and_is_idempotent(tmp_path):
    s = tmp_path / "settings.json"
    original = {"env": {"KEY": "secret-value"}, "permissions": {"allow": ["Bash(x)"]}, "model": "m",
                "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}]}}
    s.write_text(json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8")
    assert run(s) == 0
    d = read(s)
    for k in ("env", "permissions", "model"):
        assert d[k] == original[k]
    assert d["hooks"]["PreToolUse"] == original["hooks"]["PreToolUse"]
    assert count_hooks(d) == 1
    assert (tmp_path / "settings.json.pair-agent-backup").is_file()
    before = s.read_bytes()
    assert run(s) == 0
    assert s.read_bytes() == before  # 2 回目は変わらない


def test_existing_python_only_command_counts_as_present(tmp_path):
    s = tmp_path / "settings.json"
    cur = {"hooks": {"PostToolUse": [{"matcher": "Agent", "hooks": [
        {"type": "command", "command": 'python "$HOME/.claude/hooks/agent_watch_reminder.py"', "timeout": 10}]}]}}
    s.write_text(json.dumps(cur), encoding="utf-8")
    before = s.read_bytes()
    assert run(s) == 0
    assert s.read_bytes() == before  # 同じスクリプトを呼ぶ項目があれば足さない・書き換えない
    assert not (tmp_path / "settings.json.pair-agent-backup").exists()


def test_appends_into_existing_agent_matcher(tmp_path):
    s = tmp_path / "settings.json"
    cur = {"hooks": {"PostToolUse": [{"matcher": "Agent", "hooks": [{"type": "command", "command": "echo other"}]}]}}
    s.write_text(json.dumps(cur), encoding="utf-8")
    assert run(s) == 0
    entries = read(s)["hooks"]["PostToolUse"]
    assert len(entries) == 1 and len(entries[0]["hooks"]) == 2


def test_broken_json_is_not_written(tmp_path, capsys):
    s = tmp_path / "settings.json"
    s.write_text("{ not json", encoding="utf-8")
    assert run(s) == 1
    assert s.read_text(encoding="utf-8") == "{ not json"
    assert not (tmp_path / "settings.json.pair-agent-backup").exists()


def test_unexpected_shapes_are_refused(tmp_path):
    s = tmp_path / "settings.json"
    for bad in ('[]', '{"hooks": []}', '{"hooks": {"PostToolUse": {}}}', '{"hooks": {"PostToolUse": [1]}}'):
        s.write_text(bad, encoding="utf-8")
        assert run(s) == 1
        assert s.read_text(encoding="utf-8") == bad


def test_remove_only_our_entry(tmp_path):
    s = tmp_path / "settings.json"
    cur = {"model": "m", "hooks": {"PostToolUse": [{"matcher": "Agent", "hooks": [{"type": "command", "command": "echo other"}]}]}}
    s.write_text(json.dumps(cur), encoding="utf-8")
    run(s)
    assert run(s, "--remove") == 0
    assert read(s) == cur


def test_dry_run_writes_nothing(tmp_path):
    s = tmp_path / "settings.json"
    s.write_text("{}", encoding="utf-8")
    assert run(s, "--dry-run") == 0
    assert s.read_text(encoding="utf-8") == "{}"


def test_template_has_no_machine_specific_values():
    text = TEMPLATE.read_text(encoding="utf-8")
    d = json.loads(text)
    assert set(d) == {"hooks"}  # 許可・モデル・鍵を含めない
    for needle in ("C:\\", "C:/", "/Users/", "/home/", "key", "token", "secret"):
        assert needle.lower() not in text.lower(), needle
    cmd = d["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert "$HOME/.claude/hooks/agent_watch_reminder.py" in cmd
    assert "python " in cmd and "python3 " in cmd  # python が無い PC（Mac・Linux）でも python3 に落ちる


def test_hook_script_silent_and_ascii():
    out = subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"tool_name": "Agent"}),
                         capture_output=True, text=True, encoding="utf-8", timeout=20)
    assert out.returncode == 0
    msg = out.stdout
    assert msg.isascii()
    assert json.loads(msg)["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    for bad in ("", "not json", json.dumps({"tool_name": "Bash"})):
        r = subprocess.run([sys.executable, str(HOOK)], input=bad, capture_output=True, text=True, timeout=20)
        assert r.returncode == 0 and r.stdout == ""


def test_installers_ship_hook_and_merge():
    sh = (ROOT / "install.sh").read_text(encoding="utf-8")
    bat = (ROOT / "install.bat").read_text(encoding="utf-8")
    for t in (sh, bat):
        assert "agent_watch_reminder.py" in t or "hooks" in t
        assert "merge_claude_hooks.py" in t
        assert "settings-hooks.json" in t or "merge_claude_hooks.py" in t
    # Antigravity には Claude Code のフックが無いので配らない
    for line in sh.splitlines():
        if "hooks" in line and "ANTIGRAVITY" in line:
            raise AssertionError(line)
