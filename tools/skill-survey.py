#!/usr/bin/env python3
"""skill-survey.py - Survey pair-agent skill files across projects and ingest generalized results.

This script never calls an LLM. It has two stages:

  discover  走査して対象一覧（manifest・バッチ・汎化の規約）を作業ディレクトリに書く
  ingest    サブエージェントが書いた結果（out/<idx>.meta.json / .md）をライブラリへ取り込む

汎化そのもの（LLM の判断）は Claude Code のサブエージェントが担う（/skill-survey の library モード）。
"""

import argparse
import hashlib
import json
import os
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
VALID_SCORES = ("high", "medium", "low", "skip")

INSTRUCTIONS_TEMPLATE = """\
# スキル汎化の規約

`skill-survey.py discover` が書いた。サブエージェントは、この規約と担当のバッチファイル（`batch-NN.json`）だけを読む。

- バッチファイル（`batch-NN.json`）は、この instructions.md と同じフォルダにある
- 結果は、そのフォルダの `out/` に書く（絶対パスは下の「結果の書き方」）

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

- 固有のプロジェクト名・パス・環境変数名などは、概念の説明に置き換える（例: 「Mnemo で」→「この製品で」、`src/mnemo/core/hook.py` → 「先行実装」、`MNEMO_WORK_DIR` → 「データルートの環境変数」）
- `{{PROJECT_NAME}}` のようなプレースホルダは、コードの中（コードブロック・インラインコード）を除いて残さない
- 本質的なルール・原則は保持する
- 師匠（ユーザー）の発言の原文引用（`>` で始まる引用や「」内の発言）は削らずに残す。実際に踏んだ失敗・実測値・コード例も保持する。削ると「もっともらしいが使えない一般論」になる
- ユーザー名やホームディレクトリの絶対パスを本文に残さない
- フロントマターは `---` で始め、`name` / `description` / `type` / `maturity` を残す。`name` は元の値を使う（元の値に固有のプロジェクト名が入っている場合だけ、それを外した英語ケバブケースにする）
- フロントマターの source_sprint_ids, source_project, source_path, survey_date 等は削除してよい
- フロントマターの status フィールドは含めない（ingest が追加する）

## 結果の書き方（1 件ごと。`<idx>` はバッチファイルの idx）

出力先: 作業ディレクトリの `out/`（= `{out_dir}`）

1. `<idx>.meta.json` — 次の形の JSON（UTF-8）:
   `{{"idx": "<idx>", "path": "<バッチファイルの path をそのまま>", "generalizable_score": "high|medium|low|skip", "detected_specifics": ["プロジェクト固有箇所の説明（日本語）"], "notes": "追記事項・注意点"}}`
2. score が high / medium のときだけ `<idx>.md` — 汎化したスキルファイルの全文（フロントマター付き Markdown）。low / skip のときは書かない

すべて書き終えたら、idx ごとに「idx・score・一言の理由」を 1 行ずつ返して終了する。
"""

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class SurveyError(Exception):
    """続行できない状態（設定・状態ファイル・書き込みの失敗）。メッセージをそのまま利用者に出し、終了コード 1 で終わる。"""


class ConfigError(SurveyError):
    """設定ファイルが読めない、または型が違う。メッセージをそのまま利用者に出す。"""


def validate_config(cfg: dict, config_path: Path) -> None:
    """型の違いを、走査の前に止める（文字列の project_roots を 1 文字ずつ根にする等を防ぐ）。"""
    roots = cfg["project_roots"]
    if not isinstance(roots, list) or not all(isinstance(r, str) for r in roots):
        raise ConfigError(f"設定 `project_roots` は文字列の配列にしてください（今: {roots!r}）: {config_path}")
    if any(not r.strip() for r in roots):  # "" は Path("") = カレントディレクトリになってしまう
        raise ConfigError(f"設定 `project_roots` の要素は空でない文字列にしてください（今: {roots!r}）: {config_path}")
    if any(not resolve_path(r).is_absolute() for r in roots):  # 相対パスは、実行したときのカレントディレクトリで意味が変わる
        raise ConfigError(f"設定 `project_roots` の要素は絶対パス（`~` で始めてもよい）にしてください（今: {roots!r}）: {config_path}")
    depth = cfg["max_depth"]
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ConfigError(f"設定 `max_depth` は 1 以上の整数にしてください（今: {depth!r}）: {config_path}")
    out = cfg["output_dir"]
    if not isinstance(out, str) or not out.strip():  # "" は Path("") = カレントディレクトリに作業ディレクトリができる
        raise ConfigError(f"設定 `output_dir` は空でない文字列にしてください（今: {out!r}）: {config_path}")
    if not resolve_path(out).is_absolute():  # "." や ".." はカレントディレクトリ（やその親）に作業ディレクトリができてしまう
        raise ConfigError(f"設定 `output_dir` は絶対パス（`~` で始めてもよい）にしてください（今: {out!r}）: {config_path}")
    if not isinstance(cfg["also_survey_global"], bool):
        raise ConfigError(
            f"設定 `also_survey_global` は true / false にしてください（今: {cfg['also_survey_global']!r}）: {config_path}"
        )


def load_config() -> dict:
    config_path = Path.home() / ".claude" / "pair-agent" / "skill-survey-config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8-sig") as f:
                user_cfg = json.load(f)
        except (OSError, ValueError) as e:  # JSONDecodeError / UnicodeDecodeError は ValueError の仲間
            raise ConfigError(f"設定ファイルを JSON として読めません: {config_path}（{e}）")
        if not isinstance(user_cfg, dict):
            raise ConfigError(f"設定ファイルの中身が JSON オブジェクト（{{ ... }}）ではありません: {config_path}")
        cfg = {**DEFAULT_CONFIG, **user_cfg}  # 知らないキー（旧版の model 等）は読み捨てる
        validate_config(cfg, config_path)
        return cfg
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


def load_processed_state(output_dir: Path) -> tuple:
    """`.processed.json` を (処理済みパスの集合, パス → 取り込み時の中身のハッシュ) として読む。

    ファイルが無ければ空。あるのに読めない・形が違うときは SurveyError（空として扱って全件を再サーベイしない）。
    旧来の .processed.json（hashes 無し）は、ハッシュの対応が空になる。
    """
    processed_path = output_dir / ".processed.json"
    if not processed_path.exists():
        return set(), {}

    def bad(reason: str) -> SurveyError:
        return SurveyError(f"{processed_path} を使えません: {reason}（何も書かずに止めます。直すか、捨ててよければ消してください）")

    try:
        with open(processed_path, "r", encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:  # 空ファイル・壊れた JSON・文字コード違いは ValueError の仲間
        raise bad(f"JSON として読めません（{e}）")
    if not isinstance(data, dict):
        raise bad("中身が JSON オブジェクト（{ ... }）ではありません")
    processed = data.get("processed", [])
    if not isinstance(processed, list) or not all(isinstance(p, str) for p in processed):
        raise bad("`processed` が文字列の配列ではありません")
    hashes = data.get("hashes", {})
    if not isinstance(hashes, dict) or not all(isinstance(h, str) for h in hashes.values()):
        raise bad("`hashes` が「パス → ハッシュ（文字列）」のオブジェクトではありません")
    return set(processed), dict(hashes)


def processed_text(processed: set, hashes: Optional[dict] = None) -> str:
    data = {"processed": sorted(processed), "hashes": dict(sorted((hashes or {}).items()))}
    return json.dumps(data, indent=2, ensure_ascii=False)


def save_processed(output_dir: Path, processed: set, hashes: Optional[dict] = None) -> None:
    write_text_lf(output_dir / ".processed.json", processed_text(processed, hashes))


def processed_written(output_dir: Path, processed: set, hashes: Optional[dict] = None) -> bool:
    """書き込みの失敗の後で、`.processed.json` が実際に今回の中身になっているか（書けていたのに後で失敗した場合の見分け）。"""
    try:
        return (output_dir / ".processed.json").read_bytes() == processed_text(processed, hashes).encode("utf-8")
    except OSError:
        return False


def content_hash(text: str) -> str:
    """改行を LF にそろえてから取る（改行コードだけの差は同じ中身とみなす）。"""
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def write_text_lf(path: Path, text: str) -> None:
    """書くファイルの改行は常に LF（Windows の write_text は CRLF に変えてしまう）。

    一時ファイルに書いてから置き換える（アトミック）。途中で失敗しても、元のファイルは壊れない。
    """
    tmp = path.with_name(path.name + ".tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


_LINE_BREAKERS = re.compile("\r\n|[\x00-\x1f\x7f-\x9f\u2028\u2029]")  # CRLF は 1 つの空白。C0・DEL・C1（U+0085 を含む）・U+2028・U+2029 も 1 文字ずつ空白


def one_line(value) -> str:
    """レポート・index・標準出力／標準エラーの 1 行に書く文字列。改行と、ほかの制御文字（C0・C1・U+2028・U+2029）は空白に置き換える。

    meta 由来の文字列が行を壊さないように。repr の表記（`\\n` の 2 文字）にはしない。
    """
    if value is None:
        return ""
    return _LINE_BREAKERS.sub(" ", value if isinstance(value, str) else str(value))


def same_path(a, b) -> bool:
    """パスの区切り（バックスラッシュと /）と大文字小文字の違いは同じとみなす。"""
    if not isinstance(a, str) or not isinstance(b, str):
        return False
    return a.replace("\\", "/").casefold() == b.replace("\\", "/").casefold()


# ---------------------------------------------------------------------------
# Skill file helpers
# ---------------------------------------------------------------------------


def read_skill_file(path: str) -> Optional[str]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"  [warn] Could not read {one_line(path)}: {one_line(e)}")
        return None


def extract_frontmatter_field(content: str, field: str) -> str:
    # 値が空の行（`name:`）の値は空。`\s*` は改行をまたぐので使わない（次の行を値として読んでしまう）
    pattern = rf"^{re.escape(field)}:[ \t]*(.*)$"
    m = re.search(pattern, content, re.MULTILINE)
    return m.group(1).strip() if m else ""


# フロントマターの定義（有無の判定・中身の取り出し・メタデータの差し込みはすべてこれを使う）:
# 先頭の `---` 行で始まり、次の `---` だけの行（末尾の空白・CR は可）で閉じる。
_FM_OPEN = re.compile(r"---[ \t]*\r?\n")
_FM_CLOSE = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)


def frontmatter_span(content: str) -> Optional[tuple]:
    """(BOM を除いた content, 中身の開始位置, 閉じの `---` 行の開始位置)。フロントマターが無ければ None。"""
    content = content.lstrip("\ufeff")
    opened = _FM_OPEN.match(content)
    if not opened:
        return None
    closed = _FM_CLOSE.search(content, opened.end())
    if not closed:
        return None
    return content, opened.end(), closed.start()


def frontmatter_text(content: str) -> str:
    """Return the YAML frontmatter block (without the --- fences), or "" if there is none."""
    span = frontmatter_span(content)
    return span[0][span[1]:span[2]] if span else ""


def has_frontmatter(content: str) -> bool:
    """先頭の --- で始まり、--- の行で閉じる区画があるか。"""
    return frontmatter_span(content) is not None


def frontmatter_field(content: str, field: str) -> str:
    """フロントマターの中の field の値（フロントマターが無ければ ""）。本文の同名の行は拾わない。"""
    return extract_frontmatter_field(frontmatter_text(content), field)


def is_pointer_stub(content: str) -> bool:
    desc = frontmatter_field(content, "description")
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
    span = frontmatter_span(content)
    if span:
        text, _, close = span
        return text[:close] + extra + "\n" + text[close:]  # 閉じの `---` 行の直前に差し込む
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


def pending_slug(generalized_content: str, skill_info: dict) -> str:
    """pending のファイル名の本体。name から作れない（無い・`|` や記号だけで空になる）ときは、元ファイルの stem を使う。stem からも空になるときは `skill-<idx>`。

    作った名前は、必ず R13 の pending_files の規則（recorded_rel_ok）を満たす（自分で書いた控えを自分で拒否しない）。
    """
    for candidate in (frontmatter_field(generalized_content, "name"), Path(skill_info["path"]).stem):
        slug = slugify(candidate)
        if slug and recorded_rel_ok("pending", f"pending/{slug}.md"):
            return slug
    return f"skill-{skill_info.get('idx', '0')}"  # stem からも本体が空になるとき（idx は validate_manifest が [0-9A-Za-z_-] に限っている）


def plan_pending_path(generalized_content: str, skill_info: dict, output_dir: Path, reserved: set) -> Path:
    """pending に書くファイルの名前を決める。既存のファイル・ディレクトリと、予約済みの名前は避ける（-1, -2 …）。"""
    pending_dir = output_dir / "pending"
    slug = pending_slug(generalized_content, skill_info)

    candidate = pending_dir / f"{slug}.md"
    counter = 1
    while candidate.exists() or candidate.as_posix() in reserved:
        candidate = pending_dir / f"{slug}-{counter}.md"
        counter += 1
    return candidate


def write_pending_skill(
    generalized_content: str,
    skill_info: dict,
    analysis: dict,
    target: Path,
    survey_date: str,
) -> str:
    target.parent.mkdir(parents=True, exist_ok=True)
    final_content = inject_survey_metadata(generalized_content, skill_info, analysis, survey_date)
    write_text_lf(target, final_content)
    return str(target)


def index_run_mark(run_id: str) -> str:
    """index.md の節に入れる、今回の ingest を識別する印（再 ingest で同じ節を足し直さないため）。"""
    return f"<!-- skill-survey-run: {run_id} -->"


def update_index(output_dir: Path, results: list, survey_date: str, run_id: str) -> None:
    """index.md に今回の節を足す。節には run_id の印を入れ、印のある節は足し直さない（再 ingest で二重にならない）。

    印のある節に載っていない行（前回は error だったものを直して再 ingest した、など）だけは、その節の末尾に足す。
    """
    index_path = output_dir / "index.md"

    # New entries for this run: (相対パス, 行)
    new_rows = []
    for r in results:
        if r["status"] in ("pending",):
            rel = Path(r["library_path"]).relative_to(output_dir).as_posix()
            new_rows.append((rel, (
                f"| [{one_line(r['name'])}]({rel}) "
                f"| {one_line(r['project'])} "
                f"| {one_line(r.get('generalizable_score', '-'))} "
                f"| pending "
                f"| {survey_date[:10]} |"
            )))

    if not new_rows and index_path.exists():
        return  # nothing to add

    existing = index_path.read_text(encoding="utf-8") if index_path.exists() else "# Skill Library Index\n\n"

    mark = index_run_mark(run_id)
    if new_rows and mark in existing:
        # 前回の ingest が、この節を書いた後に落ちた。節は足し直さない（載っていない行だけを、その節の末尾に足す）
        start = existing.index(mark)
        end = existing.find("\n## ", start)
        end = len(existing) if end < 0 else end
        missing = [row for rel, row in new_rows if f"]({rel})" not in existing[start:end]]
        if missing:
            write_text_lf(index_path, existing[:end].rstrip("\n") + "\n" + "\n".join(missing) + "\n" + existing[end:])
        return

    if new_rows:
        section = (
            f"\n## Survey {survey_date[:10]} {mark}\n\n"  # 印は見出しの行に入れる（表の行や本文の行を増やさない）
            "| Skill | Source Project | Score | Status | Date |\n"
            "|-------|----------------|-------|--------|------|\n"
            + "\n".join(row for _, row in new_rows)
            + "\n"
        )
        write_text_lf(index_path, existing + section)
    else:
        if not index_path.exists():
            write_text_lf(index_path, existing)


def spec_lines(r: dict) -> list:
    """detected_specifics を 1 件 1 行にする（文字列 1 つや配列でないものが来ても、行を壊さない）。"""
    specs = r.get("detected_specifics") or []
    if not isinstance(specs, list):
        specs = [specs]
    return [f"  - {one_line(spec)}" for spec in specs]


def plan_report_path(output_dir: Path, survey_date: str) -> Path:
    """レポートの名前を決める（まだ書かない）。同日 2 回目以降は上書きせず、-2, -3 … の空いている名前にする。

    同名の「ファイルまたはディレクトリ」があればその名前は使わない（exists() はどちらも真）。
    """
    day = survey_date[:10]
    if not day_ok(day):  # ファイル名に入れる日付は、検めた YYYY-MM-DD だけ
        raise SurveyError(f"レポートの名前に使う日付が YYYY-MM-DD ではありません: {day!r}")
    stem = f"survey-report-{day}"
    n = 1
    while True:
        report_path = output_dir / (f"{stem}.md" if n == 1 else f"{stem}-{n}.md")
        if not report_path.exists():
            return report_path
        n += 1


def write_survey_report(
    report_path: Path, results: list, survey_date: str, total_found: int, extra_lines: Optional[list] = None
) -> Path:
    """レポートを 1 回の書き込みで作る。meta 由来の文字列の改行は空白にして、行を壊さない。"""
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
            lines.append(
                f"- **{one_line(r['name'])}** (project: `{one_line(r['project'])}`, "
                f"score: {one_line(r.get('generalizable_score', '-'))})"
            )
            if r.get("notes"):
                lines.append(f"  > {one_line(r['notes'])}")
        lines.append("")

    if skipped:
        lines += ["## Skipped — Manual Review Recommended", ""]
        for r in skipped:
            lines.append(
                f"- **{one_line(r['name'])}** (project: `{one_line(r['project'])}`, "
                f"score: {one_line(r.get('generalizable_score', '-'))})"
            )
            lines += spec_lines(r)
            if r.get("notes"):
                lines.append(f"  > {one_line(r['notes'])}")
        lines.append("")

    if errored:
        lines += ["## Errors", ""]
        for r in errored:
            lines.append(f"- `{one_line(r['path'])}`: {one_line(r.get('error', 'unknown'))}")
        lines.append("")

    text = "\n".join(lines) + (("\n".join(extra_lines) + "\n") if extra_lines else "")
    write_text_lf(report_path, text)
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
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as e:
        raise SurveyError(f"{manifest_path} を JSON として読めません（{e}）。捨ててよければ discover --force で作り直してください。")
    if not isinstance(manifest, dict):
        raise SurveyError(f"{manifest_path} の中身が JSON オブジェクトではありません。捨ててよければ discover --force で作り直してください。")
    return manifest


def save_manifest(work_dir: Path, manifest: dict) -> None:
    write_text_lf(work_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))


_IDX_OK = re.compile(r"[0-9A-Za-z_-]+")


# manifest に控える「出力先の中のパス」と日時の定義（ここだけ）。控えの検査（validate_manifest）も、書き込みの直前に控えから
# パスを作るところ（recorded_path）も、これを使う。ingest 自身が書く形だけを通す（`index.md`・`.processed.json`・
# `.survey-work/…`・`..`・絶対パス・ドライブ指定などを指す値は、形が違うので通らない）。
#   pending: `pending/<名前>.md`（pending/ の直下。区切りは `/` か `\`、1 区間目は `pending` ちょうど）。
#            名前は空でなく、`.` `..` でなく、小文字の `.md` で終わり、`:` `/` `\` と制御文字を含まない（文字種は他に制限しない）
#   report:  `survey-report-<YYYY-MM-DD>.md` か `survey-report-<YYYY-MM-DD>-<数>.md`（<数> は先頭ゼロ無しの 2 以上）。
#            日付は ingest_started_at の先頭 10 文字と一致すること
_PENDING_NAME_BAD = re.compile("[:/\\\\\x00-\x1f\x7f]")  # `:` `/` `\` と制御文字
_REPORT_FORM = re.compile(r"survey-report-([0-9]{4}-[0-9]{2}-[0-9]{2})(?:-(?:[2-9][0-9]*|[1-9][0-9]+))?\.md")
_DAY_FORM = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# ingest が控える日時（ローカル時刻を UTC オフセット付きにした `datetime.now().astimezone().isoformat()`）の形: YYYY-MM-DDTHH:MM:SS ＋ 任意の小数秒 ＋ 任意の Z か ±HH:MM
_STARTED_AT_FORM = re.compile(
    r"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?:\.[0-9]+)?(?:Z|[+-](?:[01][0-9]|2[0-3]):[0-5][0-9])?"
)


def day_ok(day) -> bool:
    """実在する YYYY-MM-DD か。"""
    if not isinstance(day, str) or not _DAY_FORM.fullmatch(day):
        return False
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def started_at_ok(value) -> bool:
    """ingest が書く形の日時か（暦に無い日付・時刻、改行や Markdown を含む値は不可）。"""
    m = _STARTED_AT_FORM.fullmatch(value) if isinstance(value, str) else None
    if not m:
        return False
    try:
        datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return False
    return True


def _pending_name(rel) -> Optional[str]:
    if not isinstance(rel, str):
        return None
    parts = rel.replace("\\", "/").split("/")
    if len(parts) != 2 or parts[0] != "pending":
        return None
    name = parts[1]
    if not name or name in (".", "..") or not name.endswith(".md") or _PENDING_NAME_BAD.search(name):
        return None
    return name


def recorded_rel_ok(kind: str, rel, started_at=None) -> bool:
    """控えの値 rel が、kind（pending / report）の形で、出力先の中を安全に指すか。report は ingest_started_at も要る。"""
    if kind == "pending":
        return _pending_name(rel) is not None
    m = _REPORT_FORM.fullmatch(rel) if isinstance(rel, str) else None
    return bool(m) and day_ok(m.group(1)) and isinstance(started_at, str) and started_at[:10] == m.group(1)


def recorded_path(output_dir: Path, kind: str, rel, started_at=None) -> Optional[Path]:
    """控えの値から書き先を作る。形が違えば None（呼ぶ側は書かずに止まる／控えが無いものとして扱う）。"""
    if not recorded_rel_ok(kind, rel, started_at):
        return None
    return output_dir / "pending" / _pending_name(rel) if kind == "pending" else output_dir / rel


def validate_manifest(manifest: dict, manifest_path: Path) -> None:
    """ingest が何かを書く前に、manifest の形を検める。違えば SurveyError（何も書かない）。

    必須: targets（要素は idx/path/project/scope が文字列）・seed_processed・stubs。
    あれば型・形を検める: hashes・控え（pending_files・report_file・ingest_started_at・output_touched）・ingested_at。
    """
    def bad(reason: str) -> SurveyError:
        return SurveyError(
            f"{manifest_path} の形が違います（{reason}）。何も書かずに止めます。"
            "捨ててよければ discover --force（途中まで取り込んだ状態なら --discard-partial）で作り直してください。"
        )

    def str_list(key: str, required: bool = True):
        if key not in manifest:
            if required:
                raise bad(f"`{key}` がありません")
            return
        v = manifest[key]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            raise bad(f"`{key}` が文字列の配列ではありません")

    targets = manifest.get("targets")
    if not isinstance(targets, list):
        raise bad("`targets` が配列ではありません")
    seen = set()
    for i, t in enumerate(targets):
        if not isinstance(t, dict) or not all(isinstance(t.get(k), str) and t[k] for k in ("idx", "path", "project", "scope")):
            raise bad(f"`targets[{i}]` が idx / path / project / scope を空でない文字列で持つオブジェクトではありません")
        if not _IDX_OK.fullmatch(t["idx"]):
            raise bad(f"`targets[{i}].idx` が使えない文字を含みます: '{one_line(t['idx'])}'")
        if t["idx"] in seen:
            raise bad(f"`targets` の idx が重複しています: '{one_line(t['idx'])}'")
        seen.add(t["idx"])
    str_list("seed_processed")
    str_list("stubs")
    # 控えのキーは、無いのは受理し、あって型が違うもの（null を含む）は拒否する（null を「欠けている」扱いにすると、index の節・レポートが二重になる）
    hashes = manifest.get("hashes", {})  # 古い manifest には無い（あれば型を検める）
    if not isinstance(hashes, dict) or not all(isinstance(h, str) for h in hashes.values()):
        raise bad("`hashes` が「パス → ハッシュ（文字列）」のオブジェクトではありません")
    pending_files = manifest.get("pending_files", {})
    if not isinstance(pending_files, dict) or not all(recorded_rel_ok("pending", v) for v in pending_files.values()):
        raise bad("`pending_files` が「idx → `pending/<名前>.md`」のオブジェクトではありません")
    if len({"pending/" + _pending_name(v).casefold() for v in pending_files.values()}) != len(pending_files):
        raise bad("`pending_files` の中で、2 つの idx が同じファイルを指しています")  # 区切りと大文字小文字の違いは同じ
    report_file = manifest.get("report_file")
    if "report_file" in manifest and not recorded_rel_ok("report", report_file, manifest.get("ingest_started_at")):
        raise bad("`report_file` が `survey-report-<YYYY-MM-DD>[-<数>].md`（日付は ingest_started_at の日付）の形ではありません")
    if "index_done" in manifest and not isinstance(manifest["index_done"], bool):
        raise bad("`index_done` が真偽値ではありません")  # 前版の控え（今は使わないが、あれば型を検める）
    if manifest.get("ingested_at") is not None and not isinstance(manifest["ingested_at"], str):
        raise bad("`ingested_at` が文字列ではありません")
    if "ingest_started_at" in manifest and not started_at_ok(manifest["ingest_started_at"]):
        raise bad("`ingest_started_at` が日時（`YYYY-MM-DDTHH:MM:SS` ＋ 任意の小数秒・`Z` か `±HH:MM`。ingest が書く形）ではありません")  # 先頭の日付がレポートの名前になる
    if "output_touched" in manifest and not isinstance(manifest["output_touched"], bool):
        raise bad("`output_touched` が真偽値ではありません")


def partial_ingest(manifest: dict) -> bool:
    """この run の ingest が出力先（pending・.processed.json・index・レポート）に書いた（書こうとした）のに、ingest 済みでない状態。

    ingest は、出力先への最初の書き込みの前に `output_touched` を True で控える（書く前に控える）。その書き込みがエラーで失敗して
    書けなかったと分かったときは、False に戻す。True のまま残るのは、控えの保存と書き込みの間でプロセスが強制終了された場合と、
    何かを書いた後で落ちた場合。何も書く前に落ちたもの（書き込みの前の拒否・dry-run を含む）には付かない。
    `output_touched` を持たない前版の manifest は、pending の控えがあれば途中とみなす。
    """
    if manifest.get("ingested_at"):
        return False
    if "output_touched" in manifest:  # 今の版の manifest: 書き込みがエラーで失敗したもの（書けなかったと分かっているもの）は、False に戻してある
        return manifest["output_touched"] is True
    pending_files = manifest.get("pending_files")
    return isinstance(pending_files, dict) and bool(pending_files)  # 前版の manifest: pending の控えがあれば途中とみなす


def written_pending_count(manifest: dict, output_dir: Path) -> int:
    """控えのある pending のうち、出力先に実際にあるファイルの数（控えは書く前に保存するので、控えの数とは違いうる）。"""
    pending_files = manifest.get("pending_files")
    if not isinstance(pending_files, dict):
        return 0
    n = 0
    for rel in pending_files.values():
        target = recorded_path(output_dir, "pending", rel)
        if target is not None and target.is_file():
            n += 1
    return n


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
    processed, recorded_hashes = load_processed_state(output_dir)  # 壊れていれば、何も書かずにここで止まる

    try:
        existing = load_manifest(work_dir)
        if existing is not None and not existing.get("ingested_at"):
            validate_manifest(existing, work_dir / "manifest.json")  # 読めても、形が違う・控えの値が拒否されるものは「壊れた」
    except SurveyError as e:
        if not (args.force or args.discard_partial):
            raise
        # 壊れた manifest（JSON として読めない・形が違う・控えの値が拒否される）は、途中まで取り込んだかを判定できない。作り直す（1 行で知らせる）
        print(f"  [warn] 壊れた manifest を捨てて作り直します。途中まで取り込んだ作業かどうかは判定できませんでした"
              f"（取り込み済みの pending が出力先に残っていると、重複しうる: {output_dir / 'pending'}）／ 理由: {one_line(e)[:200]}")
        existing = None
    partial = existing is not None and partial_ingest(existing)
    if partial and not args.discard_partial:
        # 途中まで取り込んだ作業（出力先に書いた・書こうとした）は、--force でも作り直さない（控えを失うと pending が重複する）
        written = written_pending_count(existing, output_dir)
        print(f"[skill-survey] ingest が途中まで進んだ作業が残っています: {work_dir}")
        print(f"  出力先に pending が {written} 件書き済みです（.processed.json・index・レポートを書いた後で落ちた場合もあります）。"
              "作り直すと、その控えが失われて pending が重複します。")
        print("  `skill-survey.py ingest` をやり直してください（書き済みの pending は同じファイルに書き直されます）。")
        print("  どうしても捨てるときだけ `skill-survey.py discover --discard-partial` を使ってください（書き済みの pending は残ります）。")
        return 1
    if partial:  # --discard-partial: 途中まで取り込んだ作業だけに効く
        print(f"  [warn] 途中まで取り込んだ作業を捨てて作り直します（--discard-partial）。書き済みの pending はそのまま残ります: {output_dir / 'pending'}")
    elif existing is not None and not existing.get("ingested_at") and not args.force:
        # 途中まで取り込んでいない未 ingest の作業は、--discard-partial では外れない（--force だけが外す）
        print(f"[skill-survey] まだ ingest されていない作業があります: {work_dir}")
        print("  先に `skill-survey.py ingest` を実行するか、捨ててよければ --force を付けてください。")
        if args.discard_partial:
            print("  （--discard-partial は、ingest が途中まで進んだ作業にだけ効きます。この作業は途中まで取り込まれていません。）")
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
    processed_json = output_dir / ".processed.json"
    last_ingest = processed_json.stat().st_mtime if processed_json.exists() else 0.0  # 最後に ingest した時刻

    targets, seed, stubs, already, changed, unreadable = [], [], [], 0, 0, 0
    hashes = {}  # discover の時点の中身のハッシュ（ingest が処理済みに登録するときに使う）
    for s in found:
        path = s["path"]
        content = read_skill_file(path)
        h = content_hash(content) if content is not None else None
        if path in processed:
            recorded = recorded_hashes.get(path)
            if h is None:
                print(f"  [warn] 中身を確かめられないので既処理のままにします: {path}")
                already += 1
                continue
            if recorded is None:
                # ハッシュの記録が無い旧来の登録: 最後の ingest より前の更新なら既処理。
                # この時点の中身のハッシュを manifest に控え、次の ingest で記録する。
                if Path(path).stat().st_mtime <= last_ingest:
                    hashes[path] = h
                    already += 1
                    continue
            elif recorded == h:
                already += 1
                continue
            changed += 1  # 取り込み後に中身が変わった（可能性がある）→ 既処理ではない。--since 以降の判定へ進む
        # スタブの判定は起点以前の判定より先に行う（起点以前のスタブも stubs に載せる。seed_processed にも載る）
        if content is not None and not args.include_stubs and is_pointer_stub(content):
            hashes[path] = h
            stubs.append(path)
            seed.append(path)
            continue
        if since is not None:
            mtime = datetime.fromtimestamp(Path(path).stat().st_mtime, tz=timezone.utc)
            if mtime <= since:
                seed.append(path)
                if h is not None:
                    hashes[path] = h
                continue
        if content is None:
            unreadable += 1
            continue
        hashes[path] = h
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
        "hashes": dict(sorted(hashes.items())),
        "ingested_at": None,
    }
    save_manifest(work_dir, manifest)
    write_text_lf(work_dir / "instructions.md", INSTRUCTIONS_TEMPLATE.format(out_dir=str(work_dir / "out")))

    batches = [targets[i:i + args.batch_size] for i in range(0, len(targets), args.batch_size)]
    for n, chunk in enumerate(batches, 1):
        write_text_lf(
            work_dir / f"batch-{n:02d}.json",
            json.dumps([{"idx": s["idx"], "project": s["project"], "path": s["path"]} for s in chunk],
                       indent=2, ensure_ascii=False),
        )

    print(
        f"[skill-survey] Found {len(found)} skills\n"
        f"  already processed: {already}\n"
        f"  content changed:   {changed}（処理済みだが中身が変わった。対象に戻る）\n"
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

    validate_manifest(manifest, work_dir / "manifest.json")  # 何かを書く前に形を検める（違えば何も書かずに止まる）

    # 日時は最初の ingest で manifest に控え、再 ingest でも同じ値を使う（index の印・レポートの名前・pending の日付がぶれない）
    survey_date = manifest.get("ingest_started_at") or datetime.now().astimezone().isoformat()  # 控えは validate_manifest が検め済み
    processed, hashes = load_processed_state(output_dir)  # 壊れていれば、ここで何も書かずに止まる
    results, problems = [], []

    for path in manifest["seed_processed"]:
        name = frontmatter_field(read_skill_file(path) or "", "name") or Path(path).stem
        results.append({"path": path, "status": "already_processed", "name": name})

    for s in manifest["targets"]:
        info = {"path": s["path"], "project": s["project"], "scope": s["scope"], "idx": s["idx"]}
        meta_p = work_dir / "out" / f"{s['idx']}.meta.json"
        md_p = work_dir / "out" / f"{s['idx']}.md"
        name = frontmatter_field(read_skill_file(s["path"]) or "", "name") or Path(s["path"]).stem
        try:
            analysis = json.loads(meta_p.read_text(encoding="utf-8-sig"))
            if not isinstance(analysis, dict):
                raise ValueError("JSON オブジェクトではない")
        except Exception as e:
            problems.append(f"{s['idx']} meta が読めない: {e}")
            results.append({**info, "status": "error", "error": f"meta unreadable: {e}", "name": name})
            continue
        if not same_path(analysis.get("path"), s["path"]):
            # 別のファイルの結果が、違う元ファイルに紐づくのを防ぐ（区切り文字と大文字小文字の違いは同じとみなす）
            problems.append(f"{s['idx']} meta の path が manifest と違う: '{one_line(analysis.get('path'))}'（manifest: '{one_line(s['path'])}'）")
            results.append({**info, "status": "error", "name": name,
                            "error": f"meta path mismatch: '{one_line(analysis.get('path'))}' (manifest: '{one_line(s['path'])}')"})
            continue
        score = analysis.get("generalizable_score")
        if not isinstance(score, str) or score not in VALID_SCORES:  # 完全一致（小文字）だけを受け付ける
            problems.append(f"{s['idx']} generalizable_score が不正: '{one_line(score)}'（high/medium/low/skip のどれか）")
            results.append({**info, "status": "error", "error": f"invalid generalizable_score: '{one_line(score)}'", "name": name})
            continue
        if score in ("low", "skip"):
            results.append({**info, "status": "skipped", "name": name, "generalizable_score": score,
                            "detected_specifics": analysis.get("detected_specifics", []),
                            "notes": analysis.get("notes", "")})
            continue
        if not md_p.exists():
            problems.append(f"{s['idx']} score={score} なのに .md が無い")
            results.append({**info, "status": "error", "error": "generalized content missing", "name": name})
            continue
        try:
            content = md_p.read_text(encoding="utf-8-sig")
        except Exception as e:
            problems.append(f"{s['idx']} score={score} の .md が読めない: {e}")
            results.append({**info, "status": "error", "error": f"generalized content unreadable: {e}", "name": name})
            continue
        if not content.strip():
            problems.append(f"{s['idx']} score={score} なのに .md が空")
            results.append({**info, "status": "error", "error": "generalized content empty", "name": name})
            continue
        if not has_frontmatter(content):
            problems.append(f"{s['idx']} score={score} なのに .md にフロントマターが無い")
            results.append({**info, "status": "error", "error": "generalized content has no frontmatter", "name": name})
            continue
        fm_name = frontmatter_field(content, "name")
        if not fm_name:
            problems.append(f"{s['idx']} 汎化版のフロントマターに name が無い")  # 警告（pending には書く）
        elif not slugify(fm_name):
            # `|` や記号だけで、ファイル名の本体が空になる: name が無いときと同じに、元ファイルの stem で名前を付ける
            problems.append(f"{s['idx']} 汎化版の name からファイル名を作れない（記号だけ等）。元ファイルの stem を使う")
        hits = personal_info_hits(content)
        if hits:
            problems.append(f"{s['idx']} 汎化版に個人情報らしき文字列: {', '.join(hits)}")
        results.append({**info, "status": "pending", "name": name, "content": content,
                        "analysis": analysis, "generalizable_score": score,
                        "detected_specifics": analysis.get("detected_specifics", []),
                        "notes": analysis.get("notes", "")})

    problems = [one_line(p) for p in problems]  # meta 由来の文字列の改行で、問題一覧の行を壊さない
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print(f"[skill-survey] {counts}")
    print("problems:" if problems else "problems: none")
    for p in problems:
        print("  " + p)
    if args.dry_run:
        return 0

    # ハッシュの記録が無い旧来の登録には、discover の時点の中身のハッシュを記録する（以後は中身の変化で対象に戻る）。
    # ingest 時の中身では記録しない（discover の後に変わった分を黙って吸収してしまうため）。
    manifest_hashes = manifest.get("hashes") or {}
    errored = {r["path"] for r in results if r["status"] == "error"}
    backfilled = 0
    for path in sorted(processed):
        if path not in hashes and path in manifest_hashes and path not in errored:
            hashes[path] = manifest_hashes[path]
            backfilled += 1

    # --- ここから書き込み。途中で失敗しても、再 ingest で pending が重複しないようにする ---
    # pending に書いたファイルは idx ごとに manifest の pending_files に控える（書く前に控える）。
    # 再 ingest では、控えのある idx は前回と同じファイルに書き直す。
    step = "pending の書き込み"
    pending_files = manifest.setdefault("pending_files", {})

    def recorded_target(idx):
        return recorded_path(output_dir, "pending", pending_files.get(idx))  # 形の定義は validate_manifest と同じ 1 か所

    def touch_output() -> bool:
        """出力先への最初の書き込みの前に控える（途中まで取り込んだ、の印。discover --force が作り直さないために使う）。新しく立てたら True。"""
        if manifest.get("output_touched") is True:
            return False
        manifest["output_touched"] = True
        save_manifest(work_dir, manifest)
        return True

    def untouch_output(why: str) -> None:
        """その書き込みがエラーで失敗し、書けなかったと分かったときに、印を戻す（何も書いていない作業を「途中まで」にしない）。"""
        manifest["output_touched"] = False
        try:
            save_manifest(work_dir, manifest)
        except OSError as e2:  # 戻せないときは、安全な側（途中まで取り込んだ扱い）のまま残る。黙らず知らせる
            print(f"  [warn] 出力先に書けなかった（{why}）が、manifest の `output_touched` を戻せませんでした: {one_line(e2)}。"
                  "discover --force が止まるときは --discard-partial を使ってください。")

    reserved = {t.as_posix() for t in map(recorded_target, list(pending_files)) if t is not None}

    def fail(e: OSError) -> SurveyError:
        return SurveyError(
            f"ingest が途中で失敗しました（{step}）: {one_line(e)}\n"
            "  原因を直してから、もう一度 `skill-survey.py ingest` を実行してください"
            "（書き済みの pending は同じファイルに書き直されるので、重複しません）。"
        )

    try:
        step = "manifest への控え（ingest の開始日時）"
        if not manifest.get("ingest_started_at"):
            manifest["ingest_started_at"] = survey_date
            save_manifest(work_dir, manifest)
    except OSError as e:
        raise fail(e)

    for r in results:
        if r["status"] == "pending":
            content, analysis = r.pop("content"), r.pop("analysis")
            newly, target = False, None
            try:
                newly = touch_output()
                target = recorded_target(r["idx"])
                if target is None:
                    target = plan_pending_path(content, r, output_dir, reserved)
                    reserved.add(target.as_posix())
                    pending_files[r["idx"]] = target.relative_to(output_dir).as_posix()
                    save_manifest(work_dir, manifest)
                r["library_path"] = write_pending_skill(content, r, analysis, target, survey_date)
            except OSError as e:
                if newly and not (target is not None and target.is_file()):
                    untouch_output("pending")  # 最初の書き込みが失敗して、何も書けていない（エラーで失敗したものは「書いた」に数えない）
                raise fail(e)
        if r["status"] == "error" and r["path"] in processed and r["path"] not in hashes:
            # 旧来の登録のまま変わっていた対象がエラーになった: 登録を外す（残すと次の discover で更新時刻の比較をすり抜ける）
            processed.discard(r["path"])
        if r["status"] != "error":
            processed.add(r["path"])
            # 登録するのは discover の時点の中身のハッシュ（その後に変わっていれば次の discover で対象に戻る）
            h = manifest_hashes.get(r["path"])
            if h is None:  # 古い manifest（hashes 無し）や、discover の時点で読めなかったもの
                text = read_skill_file(r["path"])
                h = content_hash(text) if text is not None else None
            if h is not None:
                hashes[r["path"]] = h
            else:
                hashes.pop(r["path"], None)

    try:
        step = ".processed.json の書き込み"
        newly = touch_output()
        try:
            save_processed(output_dir, processed, hashes)
        except OSError:
            if newly and not processed_written(output_dir, processed, hashes):
                untouch_output(".processed.json")
            raise

        # index.md・レポートは「控えてから書く」「書いたことが印で分かる」順にする。
        # どの段で落ちても、再 ingest で同じ節・同じレポートを二重に作らない。
        step = "index.md の更新"
        if manifest.get("index_done") is True:
            pass  # 前版（印を入れる前）の ingest が節を書き終えて控えた manifest。足し直すと二重になる
        else:
            update_index(output_dir, results, survey_date, survey_date)  # 節に印（run_id）を入れ、印があれば足し直さない

        step = "レポートの書き込み"
        report_path = recorded_path(output_dir, "report", manifest.get("report_file"), survey_date)
        if report_path is None or report_path.is_dir():
            # 名前を先に決めて manifest に控えてから書く。再 ingest では同じ名前に書き直す（-2 の別レポートを作らない）
            report_path = plan_report_path(output_dir, survey_date)
            manifest["report_file"] = report_path.name
            save_manifest(work_dir, manifest)
        total = len(manifest["seed_processed"]) + len(manifest["targets"])
        notes = ["", "## Run Notes", "",
                 "- 汎化は Claude Code のサブエージェントが行った（skill-survey.py は LLM を呼ばない）",
                 f"- since: {manifest.get('since') or '(指定なし)'}"]
        notes.append("- ポインタのスタブ（処理済みとして登録）:" if manifest["stubs"] else "- ポインタのスタブ: なし")
        notes += [f"  - `{one_line(p)}`" for p in manifest["stubs"]]
        if problems:
            notes += ["", "## Problems — 要確認", ""] + [f"- {p}" for p in problems]
        write_survey_report(report_path, results, survey_date, total, notes)

        step = "manifest の更新"
        manifest["ingested_at"] = survey_date
        save_manifest(work_dir, manifest)
    except OSError as e:
        raise fail(e)

    pending_count = counts.get("pending", 0)
    print(
        f"\n[skill-survey] Done!\n"
        f"  Pending skills: {pending_count}\n"
        f"  Hashes backfilled: {backfilled}\n"
        f"  Library:        {output_dir}\n"
        f"  Report:         {report_path}\n"
        f"\nRun /skill-survey --review in Claude Code to review pending skills."
    )
    return 0


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    # 標準出力が cp932 等のとき、表せない文字（絵文字など）で落ちないよう置き換えて出す
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    parser = argparse.ArgumentParser(
        prog="skill-survey.py",
        description="スキルを走査して汎化の対象を出し（discover）、汎化の結果をライブラリへ取り込む（ingest）。LLM は呼ばない。",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_disc = sub.add_parser("discover", help="走査して manifest・バッチ・汎化の規約を作業ディレクトリに書く")
    p_disc.add_argument("--since", help="この日時以前に更新されたファイルは対象にせず、処理済みとして登録する（ISO 8601）")
    p_disc.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help=f"1 バッチの件数（既定 {DEFAULT_BATCH_SIZE}）")
    p_disc.add_argument("--include-stubs", action="store_true", help="ポインタのスタブも対象にする")
    p_disc.add_argument("--force", action="store_true", help="ingest していない作業ディレクトリを捨てて作り直す（途中まで取り込んだ作業は、--discard-partial が要る）")
    p_disc.add_argument("--discard-partial", action="store_true",
                        help="ingest が途中まで進んだ作業（出力先に書き済み）だけを、控えごと捨てて作り直す（pending は重複しうる）。"
                             "途中まで取り込んでいない未 ingest の作業は、これでは捨てられない（--force を使う）")
    p_disc.set_defaults(func=cmd_discover)

    p_ing = sub.add_parser("ingest", help="out/ の結果を pending・index・レポート・.processed.json へ取り込む")
    p_ing.add_argument("--dry-run", action="store_true", help="何も書かずに件数と問題だけを出す")
    p_ing.set_defaults(func=cmd_ingest)

    args = parser.parse_args()
    try:
        return args.func(args)
    except SurveyError as e:
        print(f"[skill-survey] {e}")
        return 1
    except OSError as e:  # Traceback ではなく、何が失敗したかを出す
        print(f"[skill-survey] 失敗しました: {type(e).__name__}: {one_line(e)}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
