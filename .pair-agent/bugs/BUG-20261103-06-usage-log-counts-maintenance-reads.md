# BUG-20261103-06: 参照計装の使用ログに、本セッション内の読み出しが 108 行記録されている

- 起票日: 2026-11-03
- 状態: open（直す役に託した。対処は「## 対処」）
- 重要度: 中（TODO 12 の自動淘汰の入力が、実利用の観測になっていない）
- 分類: skill-governance / 観測
- 対象: live `usage/skill-refs.jsonl`（`~/.claude/pair-agent/usage/`・版管理しない）。記録は `tools/log_skill_ref.py`、集計は `tools/skill_usage_rollup.py`

## 症状・実測（2026-11-03 計測。見たことだけ）

- `usage/skill-refs.jsonl` は 108 行。全 108 行の session が `0e4ebe9b-f99a-4cc5-bcdc-a7888f59db43`（本セッション）。kind は全行 `read`。
- 時刻（+09:00）: 1 行目 18:43:12。2〜55 行目（54 行）は 18:56:30〜18:56:49。56〜95 行目（40 行）は 19:01:53〜19:02:37。96〜108 行目（13 行）は 19:02:58〜19:03:03。
- skill 名は、active と保留の両方にある（例: `a2a-proto-metadata-no-get` は active、`observation-analysis-must-trace-its-observation-time` は保留の stem）。
- 前の作業の記録では使用ログを「1 行」と見ていた。今のファイルの先頭は 18:43 で、それより前の行は無い。TODO 3 の確認行の所在は未確認。

## 再現手順

1. 本セッションで live `skills/*.md` を Read ツールで多数読む。
2. `usage/skill-refs.jsonl` の末尾の行の時刻と session を見る。読みの時刻と同じ範囲の行が増えている。

## 影響（事実）

- この使用ログは、実際に使われた回数ではなく、読まれた回数を数えている。今の 108 行は本セッション内の読み出しだけで、対話での利用と作業中の読みを区別していない。
- TODO 12（参照ベースの自動淘汰）の入力が、このままでは作業中の読みで汚れる。

## 証拠

- `usage/skill-refs.jsonl` の 1〜108 行（上の時刻と session）。
- `tools/log_skill_ref.py`（記録）・`tools/skill_usage_rollup.py`（集計）。

## 対処

- 2026-11-03: 直す役に託した（並列）。結果はこの節に追記する。
