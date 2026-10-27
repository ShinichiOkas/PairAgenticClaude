#!/usr/bin/env python3
"""skill-survey.py - Survey pair-agent skill files across projects and ingest generalized results.

This script never calls an LLM. It has two stages:

  discover  走査して対象一覧（manifest・バッチ・汎化の規約）を作業ディレクトリに書く
  ingest    サブエージェントが書いた結果（out/<idx>.meta.json / .md）をライブラリへ取り込む

汎化そのもの（LLM の判断）は Claude Code のサブエージェントが担う（/skill-survey の library モード）。
"""

import argparse
import json
import shutil
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "project_roots": [],
    "max_depth": 2,
    "output_dir": "~/.claude/pair-agent/skill-library",
    "also_survey_global": True,
}

WORK_DIRNAME = ".survey-work"
DEFAULT_BATCH_SIZE = 8

INSTRUCTIONS_TEMPLATE = """\
# スキル汎化の規約

`skill-survey.py discover` が書いた。サブエージェントは、この規約と担当のバッチファイル（`batch-NN.json`）だけを読む。

## 進め方

- バッチファイルの各要素（`idx` / `project` / `path`）について、`path` のスキルファイルを全文読み、1 件ずつ独立に判定・汎化する
- 読むのは担当のファイルだけ。他のファイルを探索しない

## 役割

あなたはPair Agentのスキルファイルをキュレーションする専門家です。
スキルファイルはMarkdown+YAMLフロントマター形式で書かれており、
AIと人間のペア作業における学習知識（プロセスルール、ドメイン知識、語彙など）を記録します。

## generalizable_score 基準

- high: プロジェクト固有情報がほぼなく、そのまま（または軽微な修正で）他プロジェクトで使える
- medium: プロジェクト固有情報があるが、汎化すれば十分に再利用可能
- low: プロジェクト固有情報が根幹に絡まっており、汎化すると意味が失われる恐れがある
- skip: そもそもスキルとして汎化する価値がない（一時的メモ、空ファイル等）

## プロジェクト固有情報の例

- 特定のプロジェクト名（Mnemo, ZIMLoRATrainer, rex 等）
- 絶対パスや固有のディレクトリ名
- 特定の環境変数名（MNEMO_WORK_DIR 等）
- 固有のファイルパス（src/mnemo/core/... 等）

## 汎化の方針

- 固有のプロジェクト名 → `{{PROJECT_NAME}}` または概念説明に置換
- 固有のパス → `{{PROJECT_ROOT}}/...` または概念説明に置換
- 固有の環境変数 → `{{ENV_VAR_NAME}}` に置換
- 本質的なルール・原則は保持する
- 師匠（ユーザー）の発言の原文引用（`>` で始まる引用や「」内の発言）は削らずに残す。実際に踏んだ失敗・実測値・コード例も保持する。削ると「もっともらしいが使えない一般論」になる
- ユーザー名やホームディレクトリの絶対パスを本文に残さない
- フロントマターは `---` で始め、`name` / `description` / `type` / `maturity` を残す。`name` は元の値を使う（元の値に固有のプロジェクト名が入っている場合だけ、それを外した英語ケバブケースにする）
- フロントマターの source_sprint_ids, source_project, source_path, survey_date 等は削除してよい
- フロントマターの status フィールドは含めない（ingest が追加する）

## 結果の書き方（1 件ごと。`<idx>` はバッチファイルの idx）

出力先: `{out_dir}`

1. `<idx>.meta.json` — 次の形の JSON（UTF-8）:
   `{{"idx": "<idx>", "path": "<バッチファイルの path をそのまま>", "generalizable_score": "high|medium|low|skip", "detected_specifics": ["プロジェクト固有箇所の説明（日本語）"], "notes": "追記事項・注意点"}}`
2. score が high / medium のときだけ `<idx>.md` — 汎化したスキルファイルの全文（フロントマター付き Markdown）。low / skip のときは書かない

すべて書き終えたら、idx ごとに「idx・score・一言の理由」を 1 行ずつ返して終了する。
"""

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config() -> dict:
    config_path = Path.home() / ".claude" / "pair-agent" / "skill-survey-config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8-sig") as f:
            user_cfg = json.load(f)
        return {**DEFAULT_CONFIG, **user_cfg}
    return DEFAULT_CONFIG.copy()


def resolve_path(p: str) -> Path:
    # Only a leading "~" means home. "~" inside a path (8.3 names like ABCDEF~1) must stay.
    return Path(p).expanduser()


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_project_skills(project_roots: list, max_depth: int) -> list:
    skills = []
    for root_str in project_roots:
        root = resolve_path(root_str)
        if not root.exists():
            print(f"  [warn] Project root not found: {root_str}")
            continue
        # Build glob patterns for each depth
        for depth in range(1, max_depth + 1):
            wildcard = "/".join(["*"] * depth)
            pattern = f"{wildcard}/.pair-agent/skills/*.md"
            for skill_path in root.glob(pattern):
                # Extract project name: parts between root and .pair-agent
                rel = skill_path.relative_to(root)
                pair_agent_idx = next(
                    (i for i, p in enumerate(rel.parts) if p == ".pair-agent"), None
                )
                project_name = "/".join(rel.parts[:pair_agent_idx]) if pair_agent_idx else "unknown"
                skills.append({
                    "path": str(skill_path),
                    "project": project_name,
                    "scope": "project",
                })
    return skills


def discover_global_skills(also_survey_global: bool) -> list:
    if not also_survey_global:
        return []
    skills_dir = Path.home() / ".claude" / "pair-agent" / "skills"
    if not skills_dir.exists():
        return []
    return [
        {"path": str(p), "project": "(global)", "scope": "global"}
        for p in sorted(skills_dir.glob("*.md"))
    ]


# ---------------------------------------------------------------------------
# Processed-skills tracking
# ---------------------------------------------------------------------------


def load_processed(output_dir: Path) -> set:
    processed_path = output_dir / ".processed.json"
    if processed_path.exists():
        with open(processed_path, "r", encoding="utf-8-sig") as f:
            return set(json.load(f).get("processed", []))
    return set()


def save_processed(output_dir: Path, processed: set) -> None:
    processed_path = output_dir / ".processed.json"
    with open(processed_path, "w", encoding="utf-8") as f:
        json.dump({"processed": sorted(processed)}, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Skill file helpers
# ---------------------------------------------------------------------------


def read_skill_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"  [warn] Could not read {path}: {e}")
        return None


def extract_frontmatter_field(content: str, field: str) -> str:
    pattern = rf"^{re.escape(field)}:\s*(.+)$"
    m = re.search(pattern, content, re.MULTILINE)
    return m.group(1).strip() if m else ""


def frontmatter_text(content: str) -> str:
    """Return the YAML frontmatter block (without the --- fences), or "" if there is none."""
    content = content.lstrip("﻿")
    if not content.startswith("---"):
        return ""
    end = content.find("\n---", 3)
    return content[3:end] if end != -1 else ""


def is_pointer_stub(content: str) -> bool:
    desc = extract_frontmatter_field(frontmatter_text(content), "description")
    return desc.strip("'\"").startswith("ポインタ")


def slugify(text: str) -> str:
    text = re.sub(r"[^\w\s-]", "", text.lower())
    text = re.sub(r"[\s_]+", "-", text)
    return text.strip("-")[:64]


def inject_survey_metadata(content: str, skill_info: dict, analysis: dict, survey_date: str) -> str:
    """Add survey metadata fields into the frontmatter."""
    extra = (
        f"source_project: {skill_info['project']}\n"
        f"source_path: {skill_info['path'].replace(chr(92), '/')}\n"
        f"survey_date: {survey_date[:10]}\n"
        f"generalization_score: {analysis['generalizable_score']}\n"
        f"status: pending"
    )
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[:end] + extra + "\n" + content[end:]
    # No frontmatter — create a minimal one
    return f"---\n{extra}\n---\n\n{content}"


def personal_info_hits(content: str) -> list:
    """Home path / user name fragments that should not survive generalization."""
    home = Path.home()
    user = home.name
    needles = {str(home), str(home).replace("\\", "/"), user}
    if len(user) > 8:
        needles.add(user[:6] + "~")  # 8.3 short form, e.g. ABCDEF~1
    lowered = content.lower()
    return sorted(n for n in needles if n and n.lower() in lowered)


# ---------------------------------------------------------------------------
# Library writing
# ---------------------------------------------------------------------------


def write_pending_skill(
    generalized_content: str,
    skill_info: dict,
    analysis: dict,
    output_dir: Path,
    survey_date: str,
) -> str:
    pending_dir = output_dir / "pending"
    pending_dir.mkdir(parents=True, exist_ok=True)

    name = extract_frontmatter_field(generalized_content, "name")
    if not name:
        name = Path(skill_info["path"]).stem
    slug = slugify(name)

    candidate = pending_dir / f"{slug}.md"
    counter = 1
    while candidate.exists():
        candidate = pending_dir / f"{slug}-{counter}.md"
        counter += 1

    final_content = inject_survey_metadata(generalized_content, skill_info, analysis, survey_date)
    candidate.write_text(final_content, encoding="utf-8")
    return str(candidate)


def update_index(output_dir: Path, results: list, survey_date: str) -> None:
    index_path = output_dir / "index.md"

    # New entries for this run
    new_rows = []
    for r in results:
        if r["status"] in ("pending",):
            rel = Path(r["library_path"]).relative_to(output_dir).as_posix()
            new_rows.append(
                f"| [{r['name']}]({rel}) "
                f"| {r['project']} "
                f"| {r.get('generalizable_score', '-')} "
                f"| pending "
                f"| {survey_date[:10]} |"
            )

    if not new_rows and index_path.exists():
        return  # nothing to add

    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else "# Skill Library Index\n\n"

    if new_rows:
        section = (
            f"\n## Survey {survey_date[:10]}\n\n"
            "| Skill | Source Project | Score | Status | Date |\n"
            "|-------|----------------|-------|--------|------|\n"
            + "\n".join(new_rows)
            + "\n"
        )
        index_path.write_text(existing + section, encoding="utf-8")
    else:
        if not index_path.exists():
            index_path.write_text(existing, encoding="utf-8")


def write_survey_report(output_dir: Path, results: list, survey_date: str, total_found: int) -> Path:
    report_path = output_dir / f"survey-report-{survey_date[:10]}.md"

    pending = [r for r in results if r["status"] == "pending"]
    skipped = [r for r in results if r["status"] == "skipped"]
    errored = [r for r in results if r["status"] == "error"]
    already = [r for r in results if r["status"] == "already_processed"]

    lines = [
        f"# Skill Survey Report — {survey_date[:10]}",
        "",
        "## Summary",
        "",
        f"- Total skills found: {total_found}",
        f"- Added to pending:   {len(pending)}",
        f"- Skipped (low/skip): {len(skipped)}",
        f"- Already processed:  {len(already)}",
        f"- Errors:             {len(errored)}",
        "",
    ]

    if pending:
        lines += ["## Added to Pending", ""]
        for r in pending:
            lines.append(f"- **{r['name']}** (project: `{r['project']}`, score: {r.get('generalizable_score', '-')})")
            if r.get("notes"):
                lines.append(f"  > {r['notes']}")
        lines.append("")

    if skipped:
        lines += ["## Skipped — Manual Review Recommended", ""]
        for r in skipped:
            lines.append(f"- **{r['name']}** (project: `{r['project']}`, score: {r.get('generalizable_score', '-')})")
            for spec in r.get("detected_specifics", []):
                lines.append(f"  - {spec}")
            if r.get("notes"):
                lines.append(f"  > {r['notes']}")
        lines.append("")

    if errored:
        lines += ["## Errors", ""]
        for r in errored:
            lines.append(f"- `{r['path']}`: {r.get('error', 'unknown')}")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


# ---------------------------------------------------------------------------
# Work directory
# ---------------------------------------------------------------------------


def work_dir_of(output_dir: Path) -> Path:
    return output_dir / WORK_DIRNAME


def load_manifest(work_dir: Path) -> Optional[dict]:
    manifest_path = work_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8-sig"))


def save_manifest(work_dir: Path, manifest: dict) -> None:
    (work_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def parse_since(text: str) -> datetime:
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.astimezone()  # naive → local time


# ---------------------------------------------------------------------------
# discover
# ---------------------------------------------------------------------------


def cmd_discover(args) -> int:
    config = load_config()
    output_dir = resolve_path(config["output_dir"])
    work_dir = work_dir_of(output_dir)

    existing = load_manifest(work_dir)
    if existing is not None and not existing.get("ingested_at") and not args.force:
        print(f"[skill-survey] まだ ingest されていない作業があります: {work_dir}")
        print("  先に `skill-survey.py ingest` を実行するか、捨ててよければ --force を付けてください。")
        return 1

    if args.batch_size < 1:
        print("[skill-survey] --batch-size は 1 以上にしてください。")
        return 1

    try:
        since = parse_since(args.since) if args.since else None
    except ValueError:
        print(f"[skill-survey] --since を日時として読めません: {args.since}")
        return 1

    print("[skill-survey] Discovering skill files...")
    found = discover_project_skills(config["project_roots"], config["max_depth"])
    found += discover_global_skills(config["also_survey_global"])
    processed = load_processed(output_dir)

    targets, seed, stubs, already, unreadable = [], [], [], 0, 0
    for s in found:
        path = s["path"]
        if path in processed:
            already += 1
            continue
        if since is not None:
            mtime = datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc)
            if mtime <= since:
                seed.append(path)
                continue
        content = read_skill_file(path)
        if content is None:
            unreadable += 1
            continue
        if not args.include_stubs and is_pointer_stub(content):
            stubs.append(path)
            seed.append(path)
            continue
        targets.append(s)

    targets.sort(key=lambda s: (s["project"], s["path"]))
    for i, s in enumerate(targets, 1):
        s["idx"] = f"{i:03d}"

    if work_dir.exists():
        shutil.rmtree(work_dir)
    (work_dir / "out").mkdir(parents=True)

    manifest = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "since": since.isoformat() if since else None,
        "targets": targets,
        "seed_processed": sorted(seed),
        "stubs": sorted(stubs),
        "ingested_at": None,
    }
    save_manifest(work_dir, manifest)
    (work_dir / "instructions.md").write_text(
        INSTRUCTIONS_TEMPLATE.format(out_dir=str(work_dir / "out")), encoding="utf-8"
    )

    batches = [targets[i:i + args.batch_size] for i in range(0, len(targets), args.batch_size)]
    for n, chunk in enumerate(batches, 1):
        (work_dir / f"batch-{n:02d}.json").write_text(
            json.dumps([{"idx": s["idx"], "project": s["project"], "path": s["path"]} for s in chunk],
                       indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    print(
        f"[skill-survey] Found {len(found)} skills\n"
        f"  already processed: {already}\n"
        f"  seed (<= since):   {len(seed) - len(stubs)}\n"
        f"  pointer stubs:     {len(stubs)}\n"
        f"  unreadable:        {unreadable}\n"
        f"  targets:           {len(targets)}\n"
        f"  batches:           {len(batches)} (batch size {args.batch_size})\n"
        f"  work dir:          {work_dir}"
    )
    if batches:
        print(
            "\n次: バッチごとにサブエージェントを起動し、instructions.md と batch-NN.json を渡して out/ に書かせる。"
            "\n    終わったら `skill-survey.py ingest --dry-run` → `skill-survey.py ingest`。"
        )
    return 0


# ---------------------------------------------------------------------------
# ingest
# ---------------------------------------------------------------------------


def cmd_ingest(args) -> int:
    config = load_config()
    output_dir = resolve_path(config["output_dir"])
    work_dir = work_dir_of(output_dir)

    manifest = load_manifest(work_dir)
    if manifest is None:
        print(f"[skill-survey] manifest がありません: {work_dir / 'manifest.json'}（先に discover）")
        return 1
    if manifest.get("ingested_at"):
        print(f"[skill-survey] この manifest は ingest 済みです（{manifest['ingested_at']}）。")
        return 1

    survey_date = datetime.now(timezone.utc).isoformat()
    processed = load_processed(output_dir)
    results, problems = [], []

    for path in manifest["seed_processed"]:
        name = extract_frontmatter_field(read_skill_file(path) or "", "name") or Path(path).stem
        results.append({"path": path, "status": "already_processed", "name": name})

    for s in manifest["targets"]:
        info = {"path": s["path"], "project": s["project"], "scope": s["scope"]}
        meta_p = work_dir / "out" / f"{s['idx']}.meta.json"
        md_p = work_dir / "out" / f"{s['idx']}.md"
        name = extract_frontmatter_field(read_skill_file(s["path"]) or "", "name") or Path(s["path"]).stem
        try:
            analysis = json.loads(meta_p.read_text(encoding="utf-8-sig"))
        except Exception as e:
            problems.append(f"{s['idx']} meta が読めない: {e}")
            results.append({**info, "status": "error", "error": f"meta unreadable: {e}", "name": name})
            continue
        if analysis.get("path") != s["path"]:
            problems.append(f"{s['idx']} meta の path が manifest と違う: {analysis.get('path')}")
        score = analysis.get("generalizable_score", "skip")
        if score in ("low", "skip"):
            results.append({**info, "status": "skipped", "name": name, "generalizable_score": score,
                            "detected_specifics": analysis.get("detected_specifics", []),
                            "notes": analysis.get("notes", "")})
            continue
        if not md_p.exists():
            problems.append(f"{s['idx']} score={score} なのに .md が無い")
            results.append({**info, "status": "error", "error": "generalized content missing", "name": name})
            continue
        content = md_p.read_text(encoding="utf-8-sig")
        if not content.startswith("---") or not extract_frontmatter_field(content, "name"):
            problems.append(f"{s['idx']} 汎化版にフロントマターか name が無い")
        hits = personal_info_hits(content)
        if hits:
            problems.append(f"{s['idx']} 汎化版に個人情報らしき文字列: {', '.join(hits)}")
        results.append({**info, "status": "pending", "name": name, "content": content,
                        "analysis": analysis, "generalizable_score": score,
                        "detected_specifics": analysis.get("detected_specifics", []),
                        "notes": analysis.get("notes", "")})

    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"[skill-survey] {counts}")
    print("problems:" if problems else "problems: none")
    for p in problems:
        print("  " + p)
    if args.dry_run:
        return 0

    for r in results:
        if r["status"] == "pending":
            r["library_path"] = write_pending_skill(r.pop("content"), r, r.pop("analysis"), output_dir, survey_date)
        if r["status"] != "error":
            processed.add(r["path"])

    save_processed(output_dir, processed)
    update_index(output_dir, results, survey_date)
    total = len(manifest["seed_processed"]) + len(manifest["targets"])
    report_path = write_survey_report(output_dir, results, survey_date, total)

    notes = ["", "## Run Notes", "",
             "- 汎化は Claude Code のサブエージェントが行った（skill-survey.py は LLM を呼ばない）",
             f"- since: {manifest.get('since') or '(指定なし)'}"]
    notes.append("- ポインタのスタブ（処理済みとして登録）:" if manifest["stubs"] else "- ポインタのスタブ: なし")
    notes += [f"  - `{p}`" for p in manifest["stubs"]]
    if problems:
        notes += ["", "## Problems — 要確認", ""] + [f"- {p}" for p in problems]
    with open(report_path, "a", encoding="utf-8") as f:
        f.write("\n".join(notes) + "\n")

    manifest["ingested_at"] = survey_date
    save_manifest(work_dir, manifest)

    pending_count = counts.get("pending", 0)
    print(
        f"\n[skill-survey] Done!\n"
        f"  Pending skills: {pending_count}\n"
        f"  Library:        {output_dir}\n"
        f"  Report:         {report_path}\n"
        f"\nRun /skill-survey --review in Claude Code to review pending skills."
    )
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="skill-survey.py",
        description="スキルを走査して汎化の対象を出し（discover）、汎化の結果をライブラリへ取り込む（ingest）。LLM は呼ばない。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="走査して manifest・バッチ・汎化の規約を作業ディレクトリに書く")
    p_disc.add_argument("--since", help="この日時以前に更新されたファイルは対象にせず、処理済みとして登録する（ISO 8601）")
    p_disc.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"1 バッチの件数（既定 {DEFAULT_BATCH_SIZE}）")
    p_disc.add_argument("--include-stubs", action="store_true", help="ポインタのスタブも対象にする")
    p_disc.add_argument("--force", action="store_true", help="ingest していない作業ディレクトリを捨てて作り直す")
    p_disc.set_defaults(func=cmd_discover)

    p_ing = sub.add_parser("ingest", help="out/ の結果を pending・index・レポート・.processed.json へ取り込む")
    p_ing.add_argument("--dry-run", action="store_true", help="何も書かずに件数と問題だけを出す")
    p_ing.set_defaults(func=cmd_ingest)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
