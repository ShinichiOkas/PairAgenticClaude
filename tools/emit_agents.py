#!/usr/bin/env python3
"""
成果物定義（`.mk`）＋タスクライブラリ（`.tasks`）＋ skill カタログ（`skills/`）から、
**Claude Code** および **Google Antigravity (Gemini)** のマルチエージェント書式を一括書き出しする。

Mnemo 実走成果を取り込み:
  - 費用最適化: maxTurns の厳密設定（15〜150回）とモデル割り当て最適化（sonnet/haiku適正化）
  - 文脈節約規約: 不要な全ファイル読み取り禁止・機械役の診断禁止
  - 同期担当の BOM 禁止規律
  - 実行時遮断フック: deny-map.json の自動出力（PreToolUse での物理的遮断）

使用例:
    python tools/emit_agents.py models/waterfall-core.mk
    python tools/emit_agents.py models/*.mk --target=all
    python tools/emit_agents.py models/*.mk --dest=global
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from emit_claude import Emit, Rule, base_name, dep_kind, load_slug_map  # noqa: E402
from deny_read import glob_to_regex, norm  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
NL = "\n"

# 正典 31 タスクの maxTurns と推奨モデル設定（P-54 / コスト最適化規約）
# Tier 1: 最上位高度推論 (Claude: opus, Gemini: gemini-3.1-pro)
# Tier 2: 自律エージェント基軸 (Claude: sonnet, Gemini: gemini-3.8-flash)
# Tier 3: 定型・機械的実行 (Claude: haiku, Gemini: gemini-3.8-flash)
ROLE_CONFIGS = {
    # Tier 1 (最上位高度推論)
    "design-architecture": {"max_turns": 80, "tier": 1, "claude": "opus", "gemini": "gemini-3.1-pro"},
    "decide-policy": {"max_turns": 60, "tier": 1, "claude": "opus", "gemini": "gemini-3.1-pro"},

    # Tier 2 (構築・実装・仕様・検査設計・検査実施・探針)
    "build": {"max_turns": 150, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "execute-acceptance-tests": {"max_turns": 120, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "execute-acceptance": {"max_turns": 120, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "write-specification": {"max_turns": 80, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "design-acceptance-tests": {"max_turns": 80, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "write-detailed-design": {"max_turns": 80, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "assure-design": {"max_turns": 80, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "run-probe": {"max_turns": 80, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "build-instrument": {"max_turns": 80, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "investigate": {"max_turns": 80, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "define-test-interface": {"max_turns": 60, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "estimate": {"max_turns": 60, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "reconcile-documents": {"max_turns": 60, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "file-defect": {"max_turns": 50, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "evaluate-release-condition": {"max_turns": 50, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "register-observation": {"max_turns": 50, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"},
    "elicit-intent": {"max_turns": 40, "tier": 2, "claude": "inherit", "gemini": "gemini-3.8-flash"},
    "elicit-definitions": {"max_turns": 40, "tier": 2, "claude": "inherit", "gemini": "gemini-3.8-flash"},

    # Tier 3 (同期・コミット・機械実行・非回帰・集約)
    "sync-repository": {"max_turns": 25, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "sync": {"max_turns": 25, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "run-regression": {"max_turns": 15, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "run-mutation-testing": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "package": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "publish": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "measure-baseline": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "aggregate-residual-risk": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "aggregate-track-record": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "capture-request": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "normalize-request": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "check-feasibility-envelope": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
    "extract-process-model": {"max_turns": 20, "tier": 3, "claude": "haiku", "gemini": "gemini-3.8-flash"},
}


def get_role_config(agent_name: str) -> dict:
    low = agent_name.lower()
    for k, v in ROLE_CONFIGS.items():
        if k in low:
            return v
    return {"max_turns": 80, "tier": 2, "claude": "sonnet", "gemini": "gemini-3.8-flash"}


def enhance_agent_markdown(agent_name: str, body: str, r_list: list[Rule], platform: str = "claude") -> str:
    """エージェント定義に maxTurns、モデル調整、および Mnemo の規約を注入する"""
    conf = get_role_config(agent_name)
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?(.*)$", body, re.S)
    if not m:
        return body
    fm_str, rest = m.group(1), m.group(2)

    selected_model = conf["claude"] if platform == "claude" else conf["gemini"]

    # frontmatter の調整
    lines = fm_str.splitlines()
    new_lines = []
    has_model = False
    has_max_turns = False

    for line in lines:
        if line.startswith("model:"):
            new_lines.append(f"model: {selected_model}")
            has_model = True
        elif line.startswith("maxTurns:"):
            new_lines.append(f"maxTurns: {conf['max_turns']}")
            has_max_turns = True
        else:
            new_lines.append(line)

    if not has_model:
        new_lines.append(f"model: {selected_model}")
    if not has_max_turns:
        new_lines.append(f"maxTurns: {conf['max_turns']}")

    new_fm = "\n".join(new_lines)
    tier_desc = f"Tier {conf['tier']} ({'最上位高度推論' if conf['tier'] == 1 else '自律エージェント基軸' if conf['tier'] == 2 else '定型・機械的実行'})"

    # 規約セクションの追記
    extra_rules = [
        "",
        "## 文脈の節約規約（Mnemo 実測成果）",
        "",
        f"- **モデル階層**: {tier_desc} — モデル `{selected_model}` が割り当てられています。",
        f"- **呼び出し上限 (maxTurns: {conf['max_turns']})**: 費用は「呼び出し回数 × そのときの文脈」で決まる。上限に達した場合は完了報告とともに引き継ぎ内容を出力して終了すること。",
        "- **検索パスの絞り込み**: Grep / Glob はプロジェクトルートから広範囲に打たず、必要なサブディレクトリに絞って実行すること。",
        "- **不要ファイルの読み出し禁止**: 巨大なログや無関係なモジュールを安易に読まないこと。",
    ]

    low = agent_name.lower()
    if "regression" in low:
        extra_rules.extend([
            "- ⚠ **診断の禁止**: 非回帰担当はテストを実行して合否と件数を写すのみとする。失敗時の原因診断や修正案の検討は行わない（構築者・起票者の仕事）。",
        ])
    if "sync" in low:
        extra_rules.extend([
            "- ⚠ **BOM の禁止**: git コミットメッセージには絶対に UTF-8 BOM (U+FEFF) を混入させてはならない。",
        ])

    return f"---\n{new_fm}\n---\n{rest}\n" + "\n".join(extra_rules) + "\n"


def build_workflow_meta(emission: Emit) -> dict:
    levels = emission.levels()
    nodes: dict = {}
    for r in emission.produced:
        if r.by == "human":
            continue
        agent_type = emission.names[r.node]
        nodes[r.node] = {
            "target": r.target,
            "role": r.role_name if r.is_role else ("機械（" + r.node + "）"),
            "task": r.task,
            "by": r.by,
            "agentType": agent_type,
            "gate": r.agent.get("gate"),
            "path": emission.path_of(r.node),
            "deps": [
                {
                    "name": d,
                    "node": base_name(d),
                    "kind": dep_kind(d),
                    "path": emission.path_of(base_name(d)),
                }
                for d in r.deps
            ],
            "blocks": r.blocks,
            "post": r.post,
            "out": r.out,
            "skills": emission.skills_of([r]),
        }

    human_nodes = [
        {"target": r.target, "gate": r.agent.get("gate"), "path": emission.path_of(r.node)}
        for r in emission.humans
    ]

    return {
        "model": emission.model,
        "description": f"{emission.model} の成果物 DAG（役 {len(emission.roles)} ／ 機械 {len(emission.machines)} ／ 人間ゲート {len(emission.humans)}）",
        "levels": levels,
        "nodes": nodes,
        "human": human_nodes,
    }


def emit_model(
    emission: Emit,
    target: str,
    base_dest: Path,
    dry_run: bool,
    global_deny_map: Dict[str, str],
) -> Dict[str, int]:
    counts = {"created": 0, "unchanged": 0}
    agent_files = emission.agent_files()
    all_skills = emission.skills_of(emission.work)
    skill_files = emission.skill_files(all_skills)
    wf_js = emission.workflow()
    wf_meta = build_workflow_meta(emission)
    wf_json = json.dumps(wf_meta, ensure_ascii=False, indent=2) + NL

    # deny-map の収集（物理成果物パス解決と論理名の多重防護）
    for r in emission.produced:
        if r.by != "human" and r.blocks:
            a_name = emission.names[r.node]
            globs: list[str] = []
            for b in r.blocks:
                # 1. モデル内で宣言された物理パス（agent.path）を逆引き
                phys_path = emission.path_of(b)
                if phys_path != b:
                    globs.append(phys_path.rstrip("/"))
                    if phys_path.endswith("/") or "." not in phys_path:
                        # ディレクトリの場合（"src/" に "/**" を足すと "src//**" になり Read が素通りした）
                        globs.append(f"{phys_path.rstrip('/')}/**")
                    else:
                        # ファイルの場合（例: acceptance/受入検査仕様.md）
                        # プレフィックスワイルドカードも許容して派生ファイルを防護
                        stem_prefix = phys_path.rsplit(".", 1)[0] + "*"
                        globs.append(stem_prefix)

                # 2. 論理名ベースのアクセスも防御（多重防護）
                if "/" not in b and "." not in b:
                    globs.append(f"{b}/**")
                    globs.append(f"{b}.*")
                    globs.append(f"*{b}*")
                else:
                    globs.append(b)

            # 3. 自分の deps と target に当たる glob は落とす（deps は読んでよい）。
            #    論理名の "*仕様*" が deps の "受入検査仕様.md" を塞ぎ、devops の受入検査実施者が
            #    自分の仕様を読めなかった（2026-09-17 実測）。判定はフックと同じ関数で行う
            allowed = [norm(emission.path_of(base_name(d))) for d in r.deps] + [norm(emission.path_of(r.node))]
            unique_globs = sorted(g for g in set(globs)
                                  if not any(re.search(glob_to_regex(g), p) for p in allowed))
            global_deny_map[a_name] = ",".join(unique_globs)


    def write_target(path: Path, content: str):
        if dry_run:
            print(f"  ＋ [dry-run] {path.as_posix()}")
            counts["created"] += 1
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                if path.read_text(encoding="utf-8") == content:
                    counts["unchanged"] += 1
                    return
            except Exception:
                pass
        path.write_text(content, encoding="utf-8")
        print(f"  ＋ {path.as_posix()}")
        counts["created"] += 1

    # 1. Claude Code 書式の書き出し
    if target in ("claude", "all"):
        claude_dir = base_dest / ".claude" if base_dest.name != ".claude" else base_dest
        for name, body in agent_files.items():
            enhanced = enhance_agent_markdown(name, body, emission.produced, platform="claude")
            write_target(claude_dir / "agents" / name, enhanced)
        for rel_path, body in skill_files.items():
            write_target(claude_dir / "skills" / rel_path, body)
        write_target(claude_dir / "workflows" / f"{emission.model}.js", wf_js)

    # 2. Gemini / Antigravity 書式の書き出し
    if target in ("gemini", "antigravity", "all"):
        if base_dest == Path.home():
            agents_dir = base_dest / ".gemini" / "config"
        else:
            agents_dir = base_dest / ".agents" if base_dest.name != ".agents" else base_dest

        for name, body in agent_files.items():
            enhanced = enhance_agent_markdown(name, body, emission.produced, platform="gemini")
            write_target(agents_dir / "agents" / name, enhanced)
            stem_name = Path(name).stem
            write_target(agents_dir / "skills" / stem_name / "SKILL.md", enhanced)

        for rel_path, body in skill_files.items():
            write_target(agents_dir / "skills" / rel_path, body)

        write_target(agents_dir / "workflows" / f"{emission.model}.json", wf_json)

    return counts


def claude_hook_status(claude_dir: Path, is_global: bool, register: bool, dry_run: bool) -> None:
    """deny_read.py は settings の PreToolUse に登録されて初めて動く。生成だけでは遮断は効かない。

    未登録のまま黙らない。`register` のときだけ設定へ追記する（既定では設定を書き換えない）。
    登録先はマシン固有の設定（プロジェクトなら settings.local.json）。インタプリタは
    `sys.executable` の絶対パスにする —— Windows の `python3` はストアのスタブで、黙って効かない。
    """
    candidates = [claude_dir / "settings.json"] + ([] if is_global else [claude_dir / "settings.local.json"])
    for s in candidates:
        if s.exists() and "deny_read.py" in s.read_text(encoding="utf-8", errors="replace"):
            print(f"  ✓ 遮断フックは登録済み: {s.as_posix()}")
            return

    py = Path(sys.executable).as_posix()
    if is_global:
        hooks = (claude_dir / "hooks").as_posix()
        command = f'"{py}" "{hooks}/deny_read.py" --map "{hooks}/deny-map.json"'
    else:
        base = "${CLAUDE_PROJECT_DIR:-.}/.claude/hooks"
        command = f'"{py}" "{base}/deny_read.py" --map "{base}/deny-map.json"'
    entry = {"matcher": "Read|Grep|Glob|Bash",
             "hooks": [{"type": "command", "timeout": 10, "command": command}]}
    settings = candidates[-1]

    if not register:
        print(f"\n  ⚠ 遮断フックが未登録です。このままでは blocks は宣言だけで、サブエージェントの読み取りは止まりません。")
        print(f"    登録するには --register-hook を付けて再実行するか、{settings.as_posix()} の hooks.PreToolUse に次を追記する:")
        print("    " + json.dumps(entry, ensure_ascii=False))
        return
    if dry_run:
        print(f"  ＋ [dry-run] 遮断フックを登録: {settings.as_posix()}")
        return
    data = {}
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  ⚠ {settings.as_posix()} を JSON として読めないため登録しなかった: {e}", file=sys.stderr)
            return
    data.setdefault("hooks", {}).setdefault("PreToolUse", []).append(entry)
    settings.parent.mkdir(parents=True, exist_ok=True)
    settings.write_text(json.dumps(data, ensure_ascii=False, indent=2) + NL, encoding="utf-8")
    print(f"  ＋ 遮断フックを登録: {settings.as_posix()}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Claude & Gemini マルチエージェント書式一括出力")
    parser.add_argument("models", nargs="*", help=".mk ファイル（省略時は models/*.mk 全部）")
    parser.add_argument("--target", choices=["all", "claude", "gemini", "antigravity"], default="all", help="出力対象")
    parser.add_argument("--dest", default="local", help="出力先ルート（'local' でカレント、'global' でユーザーホーム、または個別パス）")
    parser.add_argument("--dry-run", action="store_true", help="書き込まずに予定を表示")
    parser.add_argument("--register-hook", action="store_true",
                        help="遮断フック deny_read.py を Claude の settings に登録する（既定は未登録なら警告のみ）")
    args = parser.parse_args()

    if args.dest == "local":
        base_dest = ROOT
    elif args.dest == "global":
        base_dest = Path.home()
    else:
        base_dest = Path(args.dest).resolve()

    mk_files = [Path(p) for p in args.models] if args.models else sorted((ROOT / "models").glob("*.mk"))
    if not mk_files:
        print("エラー: 対象の .mk ファイルが見つかりません", file=sys.stderr)
        return 1

    print(f"# マルチエージェント書式の書き出し (target: {args.target}, dest: {base_dest})")
    total_created = 0
    total_unchanged = 0
    global_deny_map: Dict[str, str] = {}

    for mk in mk_files:
        tasks = mk.with_suffix(".tasks")
        if not tasks.exists():
            print(f"スキップ: {tasks} がありません", file=sys.stderr)
            continue
        print(f"\n## モデル: {mk.name}")
        emission = Emit(mk, tasks)
        c = emit_model(emission, args.target, base_dest, args.dry_run, global_deny_map)
        total_created += c["created"]
        total_unchanged += c["unchanged"]

        if emission.notes:
            print("\n  [所見]")
            for note in emission.notes:
                print(f"  - {note}")

    # deny-map.json の書き出し
    if global_deny_map:
        deny_json = json.dumps(global_deny_map, ensure_ascii=False, indent=2) + NL
        if args.target in ("claude", "all"):
            claude_hooks = (base_dest / ".claude" if base_dest.name != ".claude" else base_dest) / "hooks"
            if not args.dry_run:
                claude_hooks.mkdir(parents=True, exist_ok=True)
                (claude_hooks / "deny-map.json").write_text(deny_json, encoding="utf-8")
                # deny_read.py もフックディレクトリに配置
                import shutil
                shutil.copy(ROOT / "tools" / "deny_read.py", claude_hooks / "deny_read.py")
            print(f"  ＋ {claude_hooks / 'deny-map.json'}")
            total_created += 1
            claude_hook_status(claude_hooks.parent, base_dest == Path.home(), args.register_hook, args.dry_run)

        if args.target in ("gemini", "antigravity", "all"):
            if base_dest == Path.home():
                agents_hooks = base_dest / ".gemini" / "config" / "hooks"
            else:
                agents_hooks = (base_dest / ".agents" if base_dest.name != ".agents" else base_dest) / "hooks"
            if not args.dry_run:
                agents_hooks.mkdir(parents=True, exist_ok=True)
                (agents_hooks / "deny-map.json").write_text(deny_json, encoding="utf-8")
                import shutil
                shutil.copy(ROOT / "tools" / "deny_read.py", agents_hooks / "deny_read.py")
            print(f"  ＋ {agents_hooks / 'deny-map.json'}")
            total_created += 1

    print(f"\n合計: 新規/更新 {total_created} 件、変化なし {total_unchanged} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
