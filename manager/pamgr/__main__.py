"""起動口: python -m pamgr [--port N] [--no-browser]"""

from __future__ import annotations

import argparse
import threading
import webbrowser


def main() -> None:
    ap = argparse.ArgumentParser(prog="pamgr", description="Pair Agent Manager (GUI)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true", help="ブラウザを開かない")
    args = ap.parse_args()

    import uvicorn

    from .app import create_app

    url = f"http://{args.host}:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"Pair Agent Manager: {url}")
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
