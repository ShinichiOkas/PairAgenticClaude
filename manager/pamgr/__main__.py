"""起動口: python -m pamgr [--port N] [--no-browser]"""

from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    ap = argparse.ArgumentParser(prog="pamgr", description="Pair Agent Manager (GUI)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8790, help="使用中なら空いている次のポートを使う")
    ap.add_argument("--no-browser", action="store_true", help="ブラウザを開かない")
    args = ap.parse_args()

    import uvicorn

    from .app import create_app

    from . import runtime

    running = _already_running()
    if running:      # 同じデータ置き場で 2 つ動かさない（常駐が 2 つになり、同じ記録を取り合う）
        print(f"Pair Agent Manager はもう動いています: {running}")
        if not args.no_browser:
            webbrowser.open(running)
        return
    port = _free_port(args.host, args.port)
    runtime.HOST, runtime.PORT = args.host, port
    url = f"http://{args.host}:{port}/"
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Pair Agent Manager: {url}")
    from . import store
    store.save("server.json", {"url": url})
    uvicorn.run(create_app(), host=args.host, port=port, log_level="warning")


def _already_running() -> str | None:
    """このデータ置き場で動いているサーバーがあれば、その URL。"""
    import json
    import urllib.request

    from . import store
    from .paths import data_home

    url = (store.load("server.json", {}) or {}).get("url")
    if not url:
        return None
    try:
        with urllib.request.urlopen(url + "api/health", timeout=2) as r:
            h = json.loads(r.read().decode("utf-8"))
        return url if h.get("data_home") == str(data_home()) else None
    except Exception:
        return None


def _free_port(host: str, start: int) -> int:
    import socket

    for port in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex((host, port)) != 0:
                return port
    raise SystemExit(f"{start}〜{start + 19} のポートがすべて使用中です。--port で指定してください")


if __name__ == "__main__":
    main()
