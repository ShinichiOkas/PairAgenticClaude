#!/usr/bin/env python3
"""skill-library の決定性の作業をまとめた道具（LLM は呼ばない。例外は dedupe-candidates --judge-model のローカル Ollama だけ）。

師匠の宣言（2026-10-27）:「可能な限り作業は決定性のスクリプトにしろ。LLMの強さは柔軟性だがスクリプトの強さは再現性だ！」

サブコマンド:
  verify              approved/ の引用行・プレースホルダ・フロントマターを検査する（読むだけ）
  waves               未割り当ての pending を N 件ずつのグループファイルに切る
  index               index.md の各行を実ファイルの置き場所に合わせて書き直す
  promote             approved 版をグローバル Skill として書き出す
  dedupe-candidates   重複候補を文字 3-gram で出す（--judge-model でローカル Ollama 判定）

既定は下見（何も書かない）。書き込みは --apply のときだけ。書き込み前に件数・行数を検査し、合わなければ止める。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.dont_write_bytecode = True

DEFAULT_HOME = Path.home() / ".claude" / "pair-agent"


class OpsError(Exception):
    """検査に失敗して止めるときの例外（メッセージをそのまま表示して終了コード 2）。"""


# ---------------------------------------------------------------- 共通

def split_frontmatter(text: str) -> tuple[str, str]:
    """(フロントマター本文, 本文)。フロントマターが無ければ ("", text)。"""
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[1], parts[2]
    return "", text


def fm_get(fm: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", fm, re.M)
    return m.group(1).strip().strip('"') if m else ""


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


# ---------------------------------------------------------------- verify

_NORM = re.compile(r"[\s　「」『』\"'`*]")
_PLACEHOLDER = re.compile(r"\{[A-Z][A-Z0-9_]+\}")
_FENCE = re.compile(r"^[ \t]*(```|~~~).*?^[ \t]*\1[ \t]*$", re.M | re.S)
_INLINE = re.compile(r"`[^`\n]*`")


def _norm(s: str) -> str:
    return _NORM.sub("", s)


def strip_code(text: str) -> str:
    """``` ブロックと `インライン` を取り除く（コード中の {NAME} を誤検知しないため）。"""
    text = _FENCE.sub("", text)
    return _INLINE.sub("", text)


def find_placeholders(text: str) -> list[str]:
    return sorted(set(_PLACEHOLDER.findall(strip_code(text))))


def verify_file(path: Path) -> list[str]:
    t = path.read_text(encoding="utf-8")
    probs: list[str] = []
    if not t.startswith("---"):
        probs.append("frontmatter-open")
    if len(t.split("---", 2)) < 3:
        probs.append("frontmatter-close")
    fm, _ = split_frontmatter(t)
    if not re.search(r"^status: approved\s*$", t, re.M):
        probs.append("status")
    src_s = fm_get(fm, "source_path")
    src = Path(src_s) if src_s else None
    srct = src.read_text(encoding="utf-8") if src and src.is_file() else ""
    if not srct:
        probs.append("source-missing")
    src_norm = _norm(srct)
    for line in t.splitlines():
        if line.startswith(">"):
            q = _norm(line.lstrip("> "))
            if len(q) >= 6 and q not in src_norm:
                probs.append("quote-not-in-source: " + line[:80])
    ph = find_placeholders(t)
    if ph:
        probs.append("placeholders: " + " ".join(ph))
    return probs


def cmd_verify(a) -> int:
    approved = Path(a.library) / "approved"
    out = {}
    for f in sorted(approved.glob("*.md")):
        if a.approved_date and f"approved_date: {a.approved_date}" not in f.read_text(encoding="utf-8"):
            continue
        out[f.name] = {"problems": verify_file(f)}
    bad = {k: v for k, v in out.items() if v["problems"]}
    print(f"checked: {len(out)} with problems: {len(bad)}")
    for k, v in bad.items():
        print(f"\n# {k}")
        for p in v["problems"]:
            print("  -", p)
    if a.json_out:
        write_text(Path(a.json_out), json.dumps(out, ensure_ascii=False, indent=1))
    return 1 if bad else 0


# ---------------------------------------------------------------- waves

_GROUP = re.compile(r"^groupG(\d+)\.txt$")


def cmd_waves(a) -> int:
    lib = Path(a.library)
    work = Path(a.work_dir)
    review = work / "review"
    if a.size < 1:
        raise OpsError("--size は 1 以上")
    pend = sorted(p.name for p in (lib / "pending").glob("*.md"))
    asg_file = review / "assigned_global.txt"
    done = set(asg_file.read_text(encoding="utf-8").splitlines()) if asg_file.exists() else set()
    done.discard("")
    new = [f for f in pend if f not in done]
    # 番号は「既存の最大番号 + 1」。件数ベースだと欠番があるとき既存と衝突する
    nums = [int(m[1]) for p in review.glob("groupG*.txt") if (m := _GROUP.match(p.name))] if review.exists() else []
    n0 = max(nums, default=0) + 1
    full = len(new) - len(new) % a.size
    take = len(new) if a.include_remainder else full
    chunks = [new[i:i + a.size] for i in range(0, take, a.size)]
    plan = []
    for k, chunk in enumerate(chunks):
        dest = review / f"groupG{n0 + k}.txt"
        if dest.exists():
            raise OpsError(f"既存ファイルを上書きしない: {dest}")
        plan.append((n0 + k, dest, chunk))
    assigned = [f for _, _, c in plan for f in c]
    if len(assigned) != len(set(assigned)) or len(assigned) != take:
        raise OpsError("割り当て件数の検査に失敗（重複または欠落）")
    if a.apply:
        for n, dest, chunk in plan:
            write_text(dest, "\n".join(chunk) + "\n")
        if len(done | set(assigned)) != len(done) + len(assigned):
            raise OpsError("割り当て済み記録の件数が合わない")
        write_text(asg_file, "\n".join(sorted(done | set(assigned))) + "\n")
    left = len(new) - len(assigned)
    print(("書いた" if a.apply else "下見"), "| groups:", " ".join(str(n) for n, _, _ in plan) or "none",
          "| files:", len(plan), "| assigned:", len(assigned), "| unassigned left:", left)
    for n, dest, chunk in plan:
        print(f"  G{n}: {dest} ({len(chunk)} 件)")
    return 0


# ---------------------------------------------------------------- index

_ROW = re.compile(r"^\| \[(?P<name>.+?)\]\(pending/(?P<file>[^)]+)\) \|(?P<mid>.+?)\| (?P<status>pending) \|(?P<rest>.*)$")


def rewrite_index(src: str, lib: Path) -> tuple[list[str], int, int]:
    out, n_app, n_rej = [], 0, 0
    for line in src.splitlines():
        m = _ROW.match(line)
        if m:
            if (lib / "approved" / m["file"]).exists():
                line = f"| [{m['name']}](approved/{m['file']}) |{m['mid']}| approved |{m['rest']}"
                n_app += 1
            elif not (lib / "pending" / m["file"]).exists():
                line = f"| {m['name']} |{m['mid']}| rejected |{m['rest']}"
                n_rej += 1
        out.append(line)
    return out, n_app, n_rej


def cmd_index(a) -> int:
    lib = Path(a.library)
    idx = lib / "index.md"
    src = idx.read_text(encoding="utf-8")
    out, n_app, n_rej = rewrite_index(src, lib)
    n_in = len(src.splitlines())
    if len(out) != n_in:
        raise OpsError(f"行数が合わない: {n_in} -> {len(out)}")
    links = [m[1] for l in out if (m := re.search(r"\(pending/([^)]+)\)", l))]
    left = sum(not (lib / "pending" / f).exists() for f in links)
    if a.apply:
        write_text(Path(a.out) if a.out else idx, "\n".join(out) + "\n")
    print(("書いた" if a.apply else "下見"), "| lines in/out:", n_in, len(out), "| approved:", n_app,
          "rejected:", n_rej, "| dangling pending/ links:", left)
    return 0


# ---------------------------------------------------------------- promote

DROP = {"source_project", "source_path", "survey_date", "generalization_score", "status", "approved_date"}


def cmd_promote(a) -> int:
    lib = Path(a.library) / "approved"
    dest_dir = Path(a.skills_dir) if a.skills_dir else Path(a.home) / "skills"
    names = [l.strip() for l in Path(a.list).read_text(encoding="utf-8").splitlines() if l.strip()]
    files = sorted(p.name for p in lib.glob("*.md"))
    plan, problems = [], []
    for n in names:
        key = n.split("…")[0]
        hit = [f for f in files if f == n] or [f for f in files if f.startswith(key)]
        if len(hit) != 1:
            problems.append(f"対応づけ不可: {n} -> {hit}")
            continue
        t = (lib / hit[0]).read_text(encoding="utf-8")
        if a.approved_date and f"approved_date: {a.approved_date}" not in t:
            problems.append(f"指定の承認日でない: {hit[0]}")
            continue
        fm, body = split_frontmatter(t)
        if not fm:
            problems.append(f"フロントマターが無い: {hit[0]}")
            continue
        slug = Path(fm_get(fm, "source_path")).name
        if not slug or slug == ".":
            problems.append(f"source_path が無い: {hit[0]}")
            continue
        dest = dest_dir / slug
        if dest.exists():
            problems.append(f"グローバルに同名あり（書かない）: {slug} <- {hit[0]}")
            continue
        if any(slug == s for _, s, _ in plan):
            problems.append(f"候補内で書き出し名が重複: {slug} <- {hit[0]}")
            continue
        tag = (f"skill-library サーベイ {a.approved_date or '日付不明'}・元 {fm_get(fm, 'source_project') or '?'}/{slug}"
               "（Haiku 汎化＋Sonnet 修正・師匠未確認の文面）")
        lines, has_prov = [], False
        for line in fm.strip("\n").splitlines():
            k = line.split(":", 1)[0].strip()
            if k in DROP:
                continue
            if k == "provenance":
                line = line.rstrip() + "／" + tag
                has_prov = True
            lines.append(line)
        if not has_prov:
            lines.append("provenance: " + tag)
        plan.append((hit[0], slug, "---\n" + "\n".join(lines) + "\n---" + body))
    if a.apply:
        if len({s for _, s, _ in plan}) != len(plan):
            raise OpsError("書き出し名の重複")
        for _, slug, content in plan:
            write_text(dest_dir / slug, content)
        written = sum((dest_dir / s).exists() for _, s, _ in plan)
        if written != len(plan):
            raise OpsError(f"書き込み件数が合わない: {written}/{len(plan)}")
    print(("書いた" if a.apply else "下見"), len(plan), "件 / 候補", len(names), "件")
    for src, slug, _ in plan:
        print(f"  {slug}  <-  {src}")
    for p in problems:
        print("  !", p)
    if a.apply and a.record:
        write_text(Path(a.record), "\n".join(f"{s}\t{src}" for src, s, _ in plan))
    return 0


# ---------------------------------------------------------------- dedupe-candidates

PROMPT = """二つの Skill 文書を比べて、関係を一語で答える。
- 同一: 同じ主張（同じ判断基準・同じ規則）を述べている。言い回しや例が違っても同一。
- 重複あり: 主張の一部が重なるが、どちらにも相手に無い主張がある。
- 別: 別の主張を述べている。
JSON だけを返す: {"rel": "同一|重複あり|別", "why": "30字以内"}

[A] %s

[B] %s
"""


def _grams(s: str) -> set[str]:
    s = re.sub(r"[\s\W_]+", "", s.lower())
    return {s[i:i + 3] for i in range(len(s) - 2)}


def load_docs(home: Path, skills_dir: Path | None = None, library: Path | None = None) -> list[dict]:
    lib = library or home / "skill-library"
    docs = []
    for d, kind in ((lib / "approved", "approved"), (skills_dir or home / "skills", "global")):
        for f in sorted(d.glob("*.md")):
            t = f.read_text(encoding="utf-8", errors="replace")
            fm, body = split_frontmatter(t)
            docs.append({
                "kind": kind, "file": f.name, "name": fm_get(fm, "name") or f.stem, "desc": fm_get(fm, "description"),
                "src": fm_get(fm, "source_path").replace("\\", "/").lower(),
                "text": (fm_get(fm, "name") + "\n" + fm_get(fm, "description") + "\n" + re.sub(r"\s+", " ", body))[:1500],
                "path": str(f).replace("\\", "/").lower(),
            })
    return docs


def candidate_pairs(docs: list[dict], top: int) -> list[tuple[float, int, int]]:
    G = [_grams(d["name"] + d["desc"] + d["text"][:600]) for d in docs]
    pairs = []
    for i in range(len(docs)):
        best = []
        for j in range(len(docs)):
            if i >= j:
                continue
            a, b = docs[i], docs[j]
            # 汎化版とその元は除く
            if a["src"] and a["src"].endswith(b["path"].split("/pair-agent/")[-1]):
                continue
            if b["src"] and b["src"].endswith(a["path"].split("/pair-agent/")[-1]):
                continue
            if a["src"] and a["src"] == b["src"]:
                continue
            u = len(G[i] | G[j]) or 1
            best.append((len(G[i] & G[j]) / u, j))
        for s, j in sorted(best, reverse=True)[:top]:
            pairs.append((s, i, j))
    return pairs


def judge_pair(docs, p, model: str, url: str) -> dict:
    s, i, j = p
    body = json.dumps({"model": model, "prompt": PROMPT % (docs[i]["text"], docs[j]["text"]), "stream": False,
                       "format": "json", "think": False, "options": {"temperature": 0, "num_ctx": 4096}}).encode()
    req = urllib.request.Request(url.rstrip("/") + "/api/generate", data=body, headers={"Content-Type": "application/json"})
    r = json.loads(urllib.request.urlopen(req, timeout=300).read())["response"]
    try:
        v = json.loads(r)
    except Exception:
        v = {"rel": "?", "why": r[:60]}
    return {"sim": round(s, 3), "a": f'{docs[i]["kind"]}/{docs[i]["file"]}', "b": f'{docs[j]["kind"]}/{docs[j]["file"]}', **v}


def cmd_dedupe(a) -> int:
    home = Path(a.home)
    docs = load_docs(home, Path(a.skills_dir) if a.skills_dir else None, Path(a.library))
    pairs = candidate_pairs(docs, a.top)
    print("docs", len(docs), "candidate pairs", len(pairs))
    records = []
    if a.judge_model:
        # 判定先は localhost の Ollama のみ。Anthropic API は呼ばない
        with ThreadPoolExecutor(a.workers) as ex:
            futs = [ex.submit(judge_pair, docs, p, a.judge_model, a.ollama_url) for p in pairs]
            for f in as_completed(futs):
                try:
                    records.append(f.result())
                except Exception as e:  # noqa: BLE001
                    records.append({"error": str(e)[:100]})
    else:
        for s, i, j in sorted(pairs, reverse=True):
            records.append({"sim": round(s, 3), "a": f'{docs[i]["kind"]}/{docs[i]["file"]}',
                            "b": f'{docs[j]["kind"]}/{docs[j]["file"]}'})
    if a.out:
        write_text(Path(a.out), "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records))
    else:
        for r in records[:a.show]:
            print(" ", json.dumps(r, ensure_ascii=False))
    print("judged" if a.judge_model else "candidates", len(records))
    return 0


# ---------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--home", default=str(DEFAULT_HOME), help="pair-agent のホーム（既定 ~/.claude/pair-agent）")
    ap.add_argument("--library", help="skill-library（既定 <home>/skill-library）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("verify", help="approved/ を検査（読むだけ）")
    p.add_argument("--approved-date", help="この approved_date のものだけ（YYYY-MM-DD）")
    p.add_argument("--json-out", help="結果の JSON の書き出し先")
    p.set_defaults(fn=cmd_verify)

    p = sub.add_parser("waves", help="未割り当ての pending をグループファイルに切る")
    p.add_argument("--size", type=int, required=True)
    p.add_argument("--work-dir", required=True, help="review/ を持つ作業ディレクトリ")
    p.add_argument("--include-remainder", action="store_true", help="端数の件も 1 グループにする")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_waves)

    p = sub.add_parser("index", help="index.md を実ファイルの置き場所に合わせる")
    p.add_argument("--out", help="書き出し先（既定は index.md を直接）")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_index)

    p = sub.add_parser("promote", help="approved 版をグローバル Skill として書き出す")
    p.add_argument("--list", required=True, help="昇格候補の名前を 1 行 1 件で書いたファイル")
    p.add_argument("--approved-date", help="この承認日のものだけ。provenance にも入る")
    p.add_argument("--skills-dir", help="書き出し先（既定 <home>/skills）")
    p.add_argument("--record", help="--apply 時に slug<TAB>元ファイルを書き出す先")
    p.add_argument("--apply", action="store_true")
    p.set_defaults(fn=cmd_promote)

    p = sub.add_parser("dedupe-candidates", help="重複候補を出す（--judge-model でローカル Ollama 判定）")
    p.add_argument("--skills-dir", help="グローバル Skill の置き場（既定 <home>/skills）")
    p.add_argument("--top", type=int, default=3, help="各文書あたりの候補数")
    p.add_argument("--out", help="jsonl の書き出し先")
    p.add_argument("--show", type=int, default=20, help="--out なしのとき標準出力に出す件数")
    p.add_argument("--judge-model", help="指定したときだけローカル Ollama で判定する（例 qwen3.5:9b）")
    p.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    p.add_argument("--workers", type=int, default=8)
    p.set_defaults(fn=cmd_dedupe)
    return ap


def main(argv=None) -> int:
    a = build_parser().parse_args(argv)
    a.library = a.library or str(Path(a.home) / "skill-library")
    try:
        return a.fn(a)
    except OpsError as e:
        print("止めた:", e, file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
