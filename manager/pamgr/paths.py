"""場所の解決。マスター（このリポジトリ）と、マシン固有のデータ置き場。

- マスター: manager/ の親（PairAgenticClaude のリポジトリ根）。環境変数 PAMGR_MASTER で上書きできる
- データ置き場: %USERPROFILE%/.pair-agent-manager（登録簿・設定・サーベイ結果・台帳・退避）。
  マシン固有なのでリポジトリに入れない。環境変数 PAMGR_HOME で上書きできる（テストは一時フォルダ）
"""

from __future__ import annotations

import os
from pathlib import Path


def master_root() -> Path:
    env = os.environ.get("PAMGR_MASTER")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def data_home() -> Path:
    env = os.environ.get("PAMGR_HOME")
    p = Path(env).expanduser() if env else Path.home() / ".pair-agent-manager"
    p.mkdir(parents=True, exist_ok=True)
    return p


def user_home() -> Path:
    """配布先のグローバル（~/.claude・~/.gemini/config）の基点。テストでは PAMGR_USER_HOME で差し替える。"""
    env = os.environ.get("PAMGR_USER_HOME")
    return Path(env).expanduser() if env else Path.home()
