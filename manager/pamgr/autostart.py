"""ログオン時の自動起動: スタートアップに .vbs を置き、コンソール窓なしで run.bat を起動する。"""

from __future__ import annotations

import codecs
import os
from pathlib import Path

import pamgr

LAUNCHER_NAME = "PairAgentManager.vbs"


def startup_dir() -> Path:
    env = os.environ.get("PAMGR_STARTUP_DIR", "").strip()
    if env:
        return Path(env)
    appdata = os.environ.get("APPDATA", "").strip() or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def launcher_path() -> Path:
    return startup_dir() / LAUNCHER_NAME


def run_bat() -> Path:
    return Path(pamgr.__file__).resolve().parents[1] / "run.bat"


def is_enabled() -> bool:
    return launcher_path().is_file()


def _vbs_text() -> str:
    # VBS の文字列内の " は "" と書く。窓スタイル 0 = 非表示、False = 終了を待たない
    bat = str(run_bat()).replace('"', '""')
    return f'CreateObject("WScript.Shell").Run """{bat}"" --no-browser", 0, False\r\n'


def enable() -> Path:
    """.vbs を書く（あれば上書き）。WSH は BOM なし UTF-8 を読めないので UTF-16 LE（BOM 付き）。"""
    p = launcher_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(codecs.BOM_UTF16_LE + _vbs_text().encode("utf-16-le"))
    return p


def disable() -> bool:
    p = launcher_path()
    if not p.is_file():
        return False
    p.unlink()
    return True
