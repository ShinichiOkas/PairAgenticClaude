#!/usr/bin/env python3
"""
成果物 DAG ワークフロー実行ランナー（Claude & Gemini 共通）。
AgentRoleDesign のハーネス要件（H-1〜H-8）と P-53（起動の2条件）に準拠。

使用法:
    python tools/run_workflow.py waterfall-core --root=.
    python tools/run_workflow.py models/waterfall-core.mk --dry-run
    python tools/run_workflow.py .agents/workflows/waterfall-core.json --stop-at-gate
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

from check_report import check  # noqa: E402


class WorkflowRunner:
    def __init__(
        self,
        meta: Dict[str, Any],
        work_root: Path,
        dry_run: bool = False,
        stop_at_gate: bool = True,
        h8: bool = True,
    ) -> None:
        self.meta = meta
        self.work_root = work_root
        self.dry_run = dry_run
        self.stop_at_gate = stop_at_gate
        self.h8 = h8
        self.model = meta.get("model", "unknown")
        self.nodes: Dict[str, Any] = meta.get("nodes", {})
        self.levels: List[List[str]] = meta.get("levels", [])
        self.human: List[Dict[str, Any]] = meta.get("human", [])

        self.produced: List[Dict[str, Any]] = []
        self.skipped: List[Dict[str, Any]] = []
        self.unmet: List[Dict[str, Any]] = []
        self.blocked: List[Dict[str, Any]] = []
        self.outside: List[Dict[str, Any]] = []
        self.open_gates: List[Dict[str, Any]] = []
        self.halted_at: Optional[str] = None
        self.updated: Dict[str, bool] = {}

    def resolve_path(self, rel_path: str) -> Path:
        return (self.work_root / rel_path).resolve()

    def get_mtime(self, rel_path: str) -> Optional[float]:
        p = self.resolve_path(rel_path)
        if not p.exists():
            return None
        return p.stat().st_mtime

    def check_fires(self, node_key: str) -> Tuple[bool, str, bool]:
        """
        起動の 2 条件 (P-53) を判定:
          1. 実行可能条件: 必須 dep がすべて存在するか
          2. 検出条件: deps のいずれかが target より新しいか
        返り値: (run: bool, why: str, is_waiting_req: bool)
        """
        s = self.nodes.get(node_key)
        if not s:
            return False, "定義外のノード", False

        deps: List[Dict[str, Any]] = s.get("deps", [])
        other_deps = [d for d in deps if d.get("node") != node_key]

        # 1. 実行可能条件
        missing = [
            d["name"]
            for d in other_deps
            if d.get("kind") == "必須" and self.get_mtime(d["path"]) is None
        ]
        if missing:
            return False, f"必須 dep が無い: {' / '.join(missing)}", True

        # 2. 検出条件
        target_path = s.get("path", node_key)
        target_mtime = self.get_mtime(target_path)
        if target_mtime is None:
            return True, "target がまだ無い", False

        newer = []
        for d in other_deps:
            node_name = d.get("node")
            if self.updated.get(node_name):
                newer.append(d["name"])
                continue
            t = self.get_mtime(d["path"])
            if t is not None and t > target_mtime:
                newer.append(d["name"])

        if newer:
            return True, f"新しい dep: {' / '.join(newer)}", False

        return False, "deps はどれも target より新しくない", False

    def run(self) -> Dict[str, Any]:
        print(f"==================================================")
        print(f" ワークフロー実行: {self.model}")
        print(f" 作業ディレクトリ: {self.work_root}")
        print(f" 停止モード: gate={'有効' if self.stop_at_gate else '無効'}, dry-run={self.dry_run}")
        print(f"==================================================\n")

        for i, level in enumerate(self.levels):
            if self.halted_at:
                break

            phase_title = f"第{i + 1}段"
            to_run = []

            for n in level:
                fires, why, is_wait = self.check_fires(n)
                if fires:
                    to_run.append(n)
                else:
                    target_name = self.nodes[n].get("target", n)
                    self.skipped.append({"target": target_name, "why": why, "wait": is_wait})
                    print(f"  — {target_name} は走らせない（{why}）")

            if not to_run:
                continue

            print(f"\n▶ {phase_title}: {' / '.join(self.nodes[n].get('target', n) for n in to_run)}")

            for n in to_run:
                s = self.nodes[n]
                target_name = s.get("target", n)
                by = s.get("by", "agent")
                gate = s.get("gate")

                if self.dry_run:
                    print(f"  [dry-run] 起動予定: {target_name} (by: {by}, agent: {s.get('agentType')})")
                    self.produced.append({"target": target_name, "path": s.get("path"), "by": by})
                    self.updated[n] = True
                    if gate and self.stop_at_gate:
                        self.open_gates.append({"gate": gate, "target": target_name})
                        print(f"  ⏸ [dry-run] 人間ゲート {gate}: {target_name} で停止予定")
                        self.halted_at = gate
                        break
                    continue

                # 実実行
                print(f"  ▶ 実行中: {target_name} (担当: {by}, agentType: {s.get('agentType')})")
                out_path = self.resolve_path(s.get("path", target_name))

                # H-8: 実行前の内容と mtime
                old_content = None
                old_mtime = None
                if out_path.exists():
                    try:
                        old_content = out_path.read_bytes()
                        old_mtime = out_path.stat().st_mtime
                    except Exception:
                        pass

                # ここでサブエージェントまたは機械コマンドを実行
                success = self.execute_node(s)

                # H-8 チェック: 出力が不変なら mtime を巻き戻す
                if self.h8 and old_content is not None and out_path.exists():
                    try:
                        new_content = out_path.read_bytes()
                        if new_content == old_content and old_mtime is not None:
                            os.utime(out_path, (old_mtime, old_mtime))
                            print(f"    [H-8] 出力内容不変: {target_name} の mtime を維持（下流を起こさない）")
                    except Exception:
                        pass

                self.produced.append({"target": target_name, "path": s.get("path"), "by": by})
                self.updated[n] = True

                # 人間ゲートの確認
                if gate:
                    self.open_gates.append({"gate": gate, "target": target_name, "path": s.get("path")})
                    print(f"  ⏸ 人間ゲート {gate}: {target_name} —— 師匠の判定・承認が要る")
                    if self.stop_at_gate:
                        self.halted_at = gate
                        print(f"  → ゲート {gate} によりワークフローを一時停止しました。")
                        break

        # サマリー
        print("\n==================================================")
        print(" 実行サマリー")
        print("==================================================")
        if self.human:
            print(f"人間に渡すもの（by: human）: {' / '.join(h['target'] for h in self.human)}")
        print(f"生成/更新成果物: {len(self.produced)} 件")
        print(f"スキップした rule: {len(self.skipped)} 件")
        if self.open_gates:
            print(f"未決の人間ゲート: {len(self.open_gates)} 件 ({', '.join(g['gate'] for g in self.open_gates)})")
        if self.halted_at:
            print(f"停止ゲート: {self.halted_at}")

        return {
            "model": self.model,
            "produced": self.produced,
            "skipped": self.skipped,
            "open_gates": self.open_gates,
            "halted_at": self.halted_at,
        }

    def execute_node(self, node_info: Dict[str, Any]) -> bool:
        """ノードの実際の実行（サブエージェント起動またはスタブ処理）"""
        target = node_info.get("target")
        path = self.resolve_path(node_info.get("path", target))
        path.parent.mkdir(parents=True, exist_ok=True)

        if not path.exists():
            # 初期プレースホルダーを作成（実運用ではサブエージェントが生成）
            content = f"# {target}\n\n生成時刻: {time.strftime('%Y-%m-%dT%H:%M:%SZ')}\n担当: {node_info.get('role')}\n"
            path.write_text(content, encoding="utf-8")
            print(f"    作成: {path.relative_to(self.work_root)}")
        return True


def load_workflow_meta(spec: str) -> Dict[str, Any]:
    p = Path(spec)
    if p.suffix == ".json" and p.exists():
        return json.loads(p.read_text(encoding="utf-8"))

    # .mk の場合、emit_agents 経由でメタデータを取得
    if p.suffix == ".mk" or (ROOT / "models" / f"{spec}.mk").exists():
        mk_path = p if p.suffix == ".mk" else (ROOT / "models" / f"{spec}.mk")
        tasks_path = mk_path.with_suffix(".tasks")
        from emit_agents import Emit, build_workflow_meta
        emission = Emit(mk_path, tasks_path)
        return build_workflow_meta(emission)

    # .agents/workflows/<spec>.json の探索
    cand = ROOT / ".agents" / "workflows" / f"{spec}.json"
    if cand.exists():
        return json.loads(cand.read_text(encoding="utf-8"))

    raise FileNotFoundError(f"ワークフロー定義が見つかりません: {spec}")


def main() -> int:
    parser = argparse.ArgumentParser(description="マルチエージェント・ワークフロー実行ランナー")
    parser.add_argument("model", help="モデル名またはワークフロー定義ファイル (.mk / .json)")
    parser.add_argument("--root", default=".", help="作業ディレクトリ（成果物の配置先）")
    parser.add_argument("--dry-run", action="store_true", help="起動判定のみ行い実行しない")
    parser.add_argument("--no-stop", action="store_true", help="人間ゲートで停止しない")
    parser.add_argument("--no-h8", action="store_true", help="H-8（内容不変時のmtime維持）を無効化")
    args = parser.parse_args()

    try:
        meta = load_workflow_meta(args.model)
    except Exception as e:
        print(f"エラー: {e}", file=sys.stderr)
        return 1

    work_root = Path(args.root).resolve()
    runner = WorkflowRunner(
        meta=meta,
        work_root=work_root,
        dry_run=args.dry_run,
        stop_at_gate=not args.no_stop,
        h8=not args.no_h8,
    )
    res = runner.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
