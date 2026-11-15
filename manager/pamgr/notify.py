"""Windows のトースト通知: 人の判断が要るものが出たときに 1 件だけ出し、押すと GUI をその項目で開く。"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from typing import Any
from xml.sax.saxutils import escape

TIMEOUT_SEC = 20
CREATE_NO_WINDOW = 0x08000000
# Windows PowerShell 5.1 自身の通知元 ID（pwsh には WinRT の射影が無いので powershell.exe を使う）
APP_ID = r"{1AC14E77-02E7-4E5D-B744-2EB1AE5198B7}\WindowsPowerShell\v1.0\powershell.exe"
# トースト XML は base64 にして環境変数で渡す（引用符・改行の注入が起きない）
ENV_XML = "PAMGR_TOAST_XML_B64"

_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
try {
  [void][Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime]
  [void][Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime]
  $xml = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:__ENV__))
  $doc = New-Object Windows.Data.Xml.Dom.XmlDocument
  $doc.LoadXml($xml)
  $toast = [Windows.UI.Notifications.ToastNotification]::new($doc)
  [Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('__APP__').Show($toast)
} catch {
  [Console]::Error.WriteLine($_.Exception.Message)
  exit 1
}
""".replace("__ENV__", ENV_XML).replace("__APP__", APP_ID)


def build_xml(title: str, body: str, url: str) -> str:
    """トーストの XML。title・body・url は全て XML エスケープする。"""
    q = {'"': "&quot;", "'": "&apos;"}
    return (
        f'<toast activationType="protocol" launch="{escape(url, q)}">'
        '<visual><binding template="ToastGeneric">'
        f"<text>{escape(title)}</text><text>{escape(body)}</text>"
        "</binding></visual></toast>"
    )


def _encoded_script() -> str:
    return base64.b64encode(_SCRIPT.encode("utf-16-le")).decode("ascii")


def toast(title: str, body: str, url: str) -> dict[str, Any]:
    """トーストを 1 件出す。例外は投げない。"""
    if os.environ.get("PAMGR_NOTIFY", "").strip().lower() == "off":
        return {"ok": False, "skipped": True, "error": "PAMGR_NOTIFY=off"}
    if sys.platform != "win32":
        return {"ok": False, "skipped": True, "error": "Windows 以外では通知しない"}
    try:
        xml = build_xml(str(title), str(body), str(url))
        env = dict(os.environ)
        env[ENV_XML] = base64.b64encode(xml.encode("utf-8")).decode("ascii")
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", _encoded_script()],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=TIMEOUT_SEC,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", CREATE_NO_WINDOW),
            env=env,
        )
        if r.returncode != 0:
            msg = (r.stderr or r.stdout or "").strip()
            return {"ok": False, "error": msg or f"powershell.exe が {r.returncode} で終了"}
        return {"ok": True}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"{TIMEOUT_SEC} 秒でタイムアウト"}
    except Exception as e:  # noqa: BLE001 通知の失敗で本体を止めない
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
