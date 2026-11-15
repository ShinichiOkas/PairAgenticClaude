"""通知とログオン起動。トーストは本物を出さない（subprocess.run を差し替える）。スタートアップは tmp_path。"""

from __future__ import annotations

import base64
import subprocess
import xml.dom.minidom as minidom
from pathlib import Path
from types import SimpleNamespace

import pytest

from pamgr import autostart, notify


@pytest.fixture
def fake_run(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict] = []
    state = {"result": SimpleNamespace(returncode=0, stdout="", stderr=""), "raise": None}

    def run(cmd, **kw):
        calls.append({"cmd": cmd, **kw})
        if state["raise"]:
            raise state["raise"]
        return state["result"]

    monkeypatch.setattr(notify.subprocess, "run", run)
    monkeypatch.delenv("PAMGR_NOTIFY", raising=False)
    monkeypatch.setattr(notify.sys, "platform", "win32")
    return SimpleNamespace(calls=calls, state=state)


def _xml_of(call: dict) -> str:
    return base64.b64decode(call["env"][notify.ENV_XML]).decode("utf-8")


def test_toast_uses_windows_powershell_and_escapes(fake_run):
    r = notify.toast('a<&">', "b'<c>", 'http://127.0.0.1:8790/?x=1&y="2"')
    assert r == {"ok": True}
    c = fake_run.calls[0]
    assert c["cmd"][0] == "powershell.exe"
    assert "-NoProfile" in c["cmd"] and "-NonInteractive" in c["cmd"] and "-EncodedCommand" in c["cmd"]
    assert c["timeout"] == 20
    assert c["creationflags"] == 0x08000000
    xml = _xml_of(c)
    assert 'a&lt;&amp;"&gt;' in xml
    assert "b'&lt;c&gt;" in xml
    assert 'launch="http://127.0.0.1:8790/?x=1&amp;y=&quot;2&quot;"' in xml
    assert 'activationType="protocol"' in xml and 'template="ToastGeneric"' in xml
    assert xml.count("<text>") == 2
    doc = minidom.parseString(xml)  # 整形式であること
    assert doc.documentElement.getAttribute("launch") == 'http://127.0.0.1:8790/?x=1&y="2"'
    texts = [t.firstChild.data for t in doc.getElementsByTagName("text")]
    assert texts == ['a<&">', "b'<c>"]


def test_toast_script_is_encoded_and_names_app_id(fake_run):
    notify.toast("t", "b", "http://x/")
    enc = fake_run.calls[0]["cmd"][-1]
    script = base64.b64decode(enc).decode("utf-16-le")
    assert notify.APP_ID in script
    assert "ToastNotificationManager" in script
    assert "__ENV__" not in script and "__APP__" not in script


def test_toast_nonzero_exit_is_not_ok(fake_run):
    fake_run.state["result"] = SimpleNamespace(returncode=1, stdout="", stderr="boom")
    r = notify.toast("t", "b", "u")
    assert r["ok"] is False and "boom" in r["error"]


def test_toast_timeout_is_not_ok(fake_run):
    fake_run.state["raise"] = subprocess.TimeoutExpired("powershell.exe", 20)
    r = notify.toast("t", "b", "u")
    assert r["ok"] is False and "タイムアウト" in r["error"]


def test_toast_never_raises(fake_run):
    fake_run.state["raise"] = FileNotFoundError("powershell.exe")
    r = notify.toast("t", "b", "u")
    assert r["ok"] is False and "FileNotFoundError" in r["error"]


def test_toast_off_and_non_windows_skip(fake_run, monkeypatch):
    monkeypatch.setenv("PAMGR_NOTIFY", "off")
    r = notify.toast("t", "b", "u")
    assert r["ok"] is False and r["skipped"] is True
    monkeypatch.delenv("PAMGR_NOTIFY")
    monkeypatch.setattr(notify.sys, "platform", "linux")
    r = notify.toast("t", "b", "u")
    assert r["ok"] is False and r["skipped"] is True and r["error"]
    assert fake_run.calls == []


# ---- autostart ----

def test_autostart_roundtrip(tmp_path, monkeypatch):
    sd = tmp_path / "Startup"
    monkeypatch.setenv("PAMGR_STARTUP_DIR", str(sd))
    assert autostart.startup_dir() == sd
    assert autostart.launcher_path() == sd / "PairAgentManager.vbs"
    assert autostart.is_enabled() is False
    assert autostart.disable() is False

    p = autostart.enable()
    assert p == sd / "PairAgentManager.vbs" and autostart.is_enabled()
    raw = p.read_bytes()
    assert raw.startswith(b"\xff\xfe")
    text = raw.decode("utf-16")
    bat = Path(autostart.__file__).resolve().parents[1] / "run.bat"
    assert str(bat) in text
    assert "--no-browser" in text
    assert text.strip().endswith(", 0, False")
    assert 'CreateObject("WScript.Shell").Run """' in text

    assert autostart.enable() == p  # 冪等
    assert p.read_bytes() == raw
    assert autostart.disable() is True
    assert not autostart.is_enabled()
    assert list(sd.iterdir()) == []


def test_autostart_default_dir_from_appdata(tmp_path, monkeypatch):
    monkeypatch.delenv("PAMGR_STARTUP_DIR", raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "AppData"))
    assert autostart.startup_dir() == (
        tmp_path / "AppData" / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    )
