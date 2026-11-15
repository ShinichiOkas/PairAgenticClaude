"""install.bat の最後の自己検査: この venv の python か・pamgr がこの checkout を指すか・依存が入っているか。"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    here = Path(__file__).resolve().parents[1]  # manager/
    errors: list[str] = []
    venv = (here / ".venv").resolve()
    if Path(sys.prefix).resolve() != venv:
        errors.append(f"この venv の python ではない: {sys.prefix} (期待: {venv})")
    import pamgr

    if here not in Path(pamgr.__file__).resolve().parents:
        errors.append(f"pamgr がこの checkout を指していない: {pamgr.__file__}")
    try:
        import fastapi  # noqa: F401
        import omni_ai
        import uvicorn  # noqa: F401
        import yaml  # noqa: F401
        from omni_ai.providers import OllamaChatAdapter  # noqa: F401
    except ImportError as exc:
        errors.append(f"依存が欠けている: {exc}")
        omni_ai = None  # type: ignore[assignment]
    if errors:
        for e in errors:
            print("  [ERROR]", e)
        return 1
    print(f"  pamgr {pamgr.__version__} / omni_ai {omni_ai.__version__} OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
