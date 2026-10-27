"""w4 のテスト共通: skills/scripts/<名前>/<script>.py を読み込む。"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(skill: str, script: str):
    p = ROOT / "skills" / "scripts" / skill / script
    spec = importlib.util.spec_from_file_location("w4_" + p.stem, p)
    assert spec is not None and spec.loader is not None
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m
