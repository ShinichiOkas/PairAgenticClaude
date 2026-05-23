#!/usr/bin/env python3
"""skill-survey.py - Survey and generalize pair-agent skill files across projects."""

import json
import os
import sys
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

try:
    import anthropic
except ImportError:
    print("Error: anthropic package not found. Install with: pip install anthropic")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "project_roots": [],
    "max_depth": 2,
    "output_dir": "~/.claude/pair-agent/skill-library",
    "model": "claude-haiku-4-5-20251001",
    "also_survey_global": True,
}

SYSTEM_PROMPT = """\
あなたはPair Agentのスキルファイルをキュレーションする専門家です。
スキルファイルはMarkdown+YAMLフロントマター形式で書かれており、
AIと人間のペア作業における学習知識（プロセスルール、ドメイン知識、語彙など）を記録します。

スキルファイルを分析して、以下をJSON形式のみで返してください（説明文は不要）:

{
  "generalizable_score": "high|medium|low|skip",
  "detected_specifics": ["プロジェクト固有箇所の説明（日本語）"],
  "generalized_content": "汎化したスキルファイルの全文（Markdown）",
  "notes": "追記事項・注意点"
}

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

- 固有のプロジェクト名 → `{PROJECT_NAME}` または概念説明に置換
- 固有のパス → `{PROJECT_ROOT}/...` または概念説明に置換
- 固有の環境変数 → `{ENV_VAR_NAME}` に置換
- 本質的なルール・原則は保持する
- フロントマターの source_sprint_ids, source_project, source_path, survey_date 等は削除してよい
- フロントマターの status フィールドは含めない（呼び出し元が追加する）
"""

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


def load_config() -> dict:
    config_path = Path.home() / ".claude" / "pair-agent" / "skill-survey-config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        return {**DEFAULT_CONFIG, **user_cfg}
    return DEFAULT_CONFIG.copy()


def resolve_path(p: str) -> Path:
    return Path(p.replace("~", str(Path.home())))


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def discover_project_skills(project_roots: list, max_depth: int) -> list:
    skills = []
    for root_str in project_roots:
        root = Path(root_str)
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
        with open(processed_path, "r", encoding="utf-8") as f:
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


# ---------------------------------------------------------------------------
# Claude API analysis
# ---------------------------------------------------------------------------


def analyze_skill(content: str, skill_info: dict, client: anthropic.Anthropic, model: str) -> Optional[dict]:
    user_msg = (
        f"以下のスキルファイルを分析してください。\n\n"
        f"プロジェクト: {skill_info['project']}\n"
        f"スコープ: {skill_info['scope']}\n"
        f"パス: {skill_info['path']}\n\n"
        f"---\n\n{content}"
    )
    try:
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=[
                {
                    "type": "text",
                    "text": SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        # Extract JSON block if wrapped in code fences
        m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
        if m:
            raw = m.group(1)
        else:
            # Try bare JSON object
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                raw = m.group(0)
        return json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"  [warn] JSON parse error for {skill_info['path']}: {e}")
        return None
    except Exception as e:
        print(f"  [error] API call failed for {skill_info['path']}: {e}")
        return None


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
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("[skill-survey] Loading config...")
    config = load_config()

    output_dir = resolve_path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "pending").mkdir(exist_ok=True)
    (output_dir / "approved").mkdir(exist_ok=True)

    survey_date = datetime.now(timezone.utc).isoformat()

    print("[skill-survey] Discovering skill files...")
    project_skills = discover_project_skills(config["project_roots"], config["max_depth"])
    global_skills = discover_global_skills(config["also_survey_global"])
    all_skills = project_skills + global_skills
    total = len(all_skills)

    print(
        f"[skill-survey] Found {total} skills "
        f"({len(project_skills)} project, {len(global_skills)} global)"
    )

    if total == 0:
        print("[skill-survey] Nothing to process. Check project_roots in config.")
        return

    processed = load_processed(output_dir)
    client = anthropic.Anthropic()
    results = []

    for skill_info in all_skills:
        path = skill_info["path"]
        print(f"\n  Analyzing: {path}")

        if path in processed:
            print("    → already processed, skipping")
            name = extract_frontmatter_field(read_skill_file(path) or "", "name") or Path(path).stem
            results.append({**skill_info, "status": "already_processed", "name": name})
            continue

        content = read_skill_file(path)
        if content is None:
            results.append({**skill_info, "status": "error", "error": "could not read file", "name": Path(path).stem})
            continue

        skill_info["original_content"] = content
        analysis = analyze_skill(content, skill_info, client, config["model"])

        name = extract_frontmatter_field(content, "name") or Path(path).stem

        if analysis is None:
            results.append({**skill_info, "status": "error", "error": "analysis failed", "name": name})
            continue

        score = analysis.get("generalizable_score", "skip")
        print(f"    → score: {score}")

        if score in ("low", "skip"):
            processed.add(path)
            results.append({
                **skill_info,
                "status": "skipped",
                "name": name,
                "generalizable_score": score,
                "detected_specifics": analysis.get("detected_specifics", []),
                "notes": analysis.get("notes", ""),
            })
            continue

        library_path = write_pending_skill(
            analysis["generalized_content"], skill_info, analysis, output_dir, survey_date
        )
        print(f"    → pending: {library_path}")
        processed.add(path)

        results.append({
            **skill_info,
            "status": "pending",
            "name": name,
            "library_path": library_path,
            "generalizable_score": score,
            "detected_specifics": analysis.get("detected_specifics", []),
            "notes": analysis.get("notes", ""),
        })

    save_processed(output_dir, processed)
    print("\n[skill-survey] Updating index and writing report...")
    update_index(output_dir, results, survey_date)
    report_path = write_survey_report(output_dir, results, survey_date, total)

    pending_count = sum(1 for r in results if r["status"] == "pending")
    print(
        f"\n[skill-survey] Done!\n"
        f"  Pending skills: {pending_count}\n"
        f"  Library:        {output_dir}\n"
        f"  Report:         {report_path}\n"
        f"\nRun /skill-survey in Claude Code to review pending skills."
    )


if __name__ == "__main__":
    main()
