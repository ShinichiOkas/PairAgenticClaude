"""動いているサーバーの口（通知を押したときに開く URL のため）。__main__ が起動時に書く。"""

from __future__ import annotations

HOST = "127.0.0.1"
PORT = 8790


def base_url() -> str:
    return f"http://{HOST}:{PORT}/"
