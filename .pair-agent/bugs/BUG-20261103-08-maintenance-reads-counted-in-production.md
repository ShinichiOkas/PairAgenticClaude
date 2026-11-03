# BUG-20261103-08: 使用ログに、skill を編集した本セッションの読みが残り、集計がそれを利用として数える

- 起票日: 2026-11-03
- 状態: open（起票時点。直す役を並列で起動。対処は「## 対処」）
- 重要度: 中（TODO 12 の自動淘汰の入力が、保守の読みで汚れる。BUG-20261103-06 と同じ型）
- 分類: skill-governance / 観測
- 対象: live `usage/skill-refs.jsonl`（`~/.claude/pair-agent/usage/`・版管理しない）。記録 `tools/log_skill_ref.py`、集計 `tools/skill_usage_rollup.py`、フック設定 `~/.claude/settings.json`（PostToolUse）
- 前例: BUG-20261103-06（108 行が同じ型）。規則 `usage-count-excludes-maintenance-reads`（main `.pair-agent/skills/`・forming）は、保守の読みを利用から外し、除外件数を出すことを求める

## 症状・実測（2026-11-03 計測。見たことだけ）

- 使用ログは 14 行。全 14 行が session `0e4ebe9b-f99a-4cc5-bcdc-a7888f59db43`（本セッション）。cwd は全行 `C:\Users\0000950207\work\PairAgenticClaude`。
- 集計（`skill_usage_rollup.py`・exit 0）: `skills=259 referenced=7 log_lines=14 excluded_bulk=0 burst=10/10s unmatched=1 malformed=0`。
- 読み（kind `read`）は 13 件。そのうち 8 件は、本セッションが後に編集した同じファイルの読み。集計はこの 8 件を read_count に数えている:
  - harness-exit-code-must-reflect-failure: 21:57:17・22:01:28・22:04:32（3 件）。同じファイルの編集コミット d5568fb が 22:07:10。
  - verified-means-it-ran-not-that-it-ran-as-intended: 21:57:17・22:01:28・22:04:32（3 件）。編集コミット a4600d8 が 22:07:06。
  - own-inference-is-not-measured-fact: 21:57:53・22:04:32（2 件）。編集コミット 40d3481 が 22:07:02。
- 残り 5 件（commit-small-per-boundary 2 件・file-bug-ticket-for-unrelated-discovery 1 件・reread-before-reporting-live-state 1 件・todo-and-plan-as-baseline-not-experimental 1 件）は、本セッションでそのファイルを編集していない。利用か保守かは、この記録だけでは決められない。
- Skill の起動は 1 件（retrospect・21:56:25・kind `skill`）。集計の `unmatched=1` に入る。
- 記録に Edit・Write の行は 1 件も無い。編集の事実は使用ログに残っていない。
- 記録の仕組み（コードで確認した事実）:
  - `tools/log_skill_ref.py` が扱う `tool_name` は `Read`（skills/ 配下の .md・行 69）と `Skill`（行 73）だけ。Edit・Write・MultiEdit の分岐は無い。
  - `~/.claude/settings.json` の PostToolUse の matcher は `Read|Skill`（行 95）。
  - `tools/skill_usage_rollup.py` の除外は `excluded_bulk`（一括読み）だけ。保守の読みの区分も、その件数も出ない。
- 参考: live `master` は d5568fb（clean）。main は 675e137（clean）。

## 再現手順

1. skill 本文を Read し、そのファイルを Edit する（本セッションの作業と同じ形）。
2. `usage/skill-refs.jsonl` の末尾を見る。Read の行は増え、Edit の行は増えない。
3. `python tools/skill_usage_rollup.py` を回す。編集したファイルの read_count に、その Read が数えられる。

注: 再現は本番ログを汚す。試験は写し（コピー）のログで行うこと。

## 影響（事実）

- 本番ログの 14 行は、全部が本セッション（保守作業）の記録。実利用の観測ではない。
- 編集した 3 件の read_count は、保守の読みの分だけ多く出ている（3・3・2）。
- TODO 12（参照ベースの自動淘汰）の入力が、保守の読みで汚れている。
- BUG-20261103-06 の一括読みの規則では、この 8 件は除かれない（excluded_bulk=0）。

## 証拠

- `usage/skill-refs.jsonl` の 1〜14 行（上の時刻と session）。
- 編集コミット: 40d3481（22:07:02・own-inference）、a4600d8（22:07:06・verified-means）、d5568fb（22:07:10・harness-exit-code）。`git log` の commit 時刻（+09:00）。
- `tools/log_skill_ref.py` 行 59・69・73・81、`~/.claude/settings.json` 行 95、`tools/skill_usage_rollup.py` の `excluded_bulk` 出力（行 135・154）。
- 規則 `.pair-agent/skills/usage-count-excludes-maintenance-reads.md`（main・450b429）。

## 対処

- 起票時点では未着手。直す役を並列で起動する（2026-11-03）。直した後の SHA と件数は、この節に追記する。

## 未確認

- Bash の読みで、フックが発火するかは未確認（本セッションの Bash 経由の読みは記録に無い）。
- 「保守の読み」を機械で何と定義するかは、直す役が決める。この票では決めない。
- subagent の `agent_type` は null しか見ていない（本セッションは main のみ）。
- 残り 5 件が利用か保守かは、記録からは決められない。
- 他のセッション・他の PC・他のプロジェクトで同じ型が出ているかは未確認（本番ログは本 PC の 1 本だけ）。
