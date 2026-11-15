"""テストは実データ（~/.claude・~/.gemini・兄弟リポジトリ）に書かない。
PAMGR_HOME（データ置き場）と PAMGR_USER_HOME（配布先のホーム）を一時フォルダに向ける。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("PAMGR_HOME", str(tmp_path / "pamgr-home"))
    monkeypatch.setenv("PAMGR_USER_HOME", str(tmp_path / "userhome"))
    (tmp_path / "userhome").mkdir()
    return tmp_path


@pytest.fixture
def client() -> TestClient:
    from pamgr.app import create_app

    return TestClient(create_app())
