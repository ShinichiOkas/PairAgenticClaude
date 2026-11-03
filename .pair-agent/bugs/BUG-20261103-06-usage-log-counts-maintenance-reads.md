# BUG-20261103-06: 参照計装の使用ログに、本セッション内の読み出しが 108 行記録されている

- 起票日: 2026-11-03
- 状態: fixed（2026-11-03・`eea9462`・`b3a42ed`。ただし `cwd`・`agent_type` は本物のフック入力で未確認。対処は「## 対処」）
- 重要度: 中（TODO 12 の自動淘汰の入力が、実利用の観測になっていない）
- 分類: skill-governance / 観測
- 対象: live `usage/skill-refs.jsonl`（`~/.claude/pair-agent/usage/`・版管理しない）。記録は `tools/log_skill_ref.py`、集計は `tools/skill_usage_rollup.py`

## 症状・実測（2026-11-03 計測。見たことだけ）

- `usage/skill-refs.jsonl` は 108 行。全 108 行の session が `0e4ebe9b-f99a-4cc5-bcdc-a7888f59db43`（本セッション）。kind は全行 `read`。
- 時刻（+09:00）のまとまり（10 秒超の空きで区切る）: 1 行目 18:43:12。2〜55 行目（54 行）18:56:30〜18:56:49。56〜68 行目（13 行）19:01:53〜19:01:58。69〜81 行目（13 行）19:02:14〜19:02:19。82〜95 行目（14 行）19:02:32〜19:02:37。96〜108 行目（13 行）19:02:58〜19:03:03。
- 名前は 107 種（`a2a-proto-metadata-no-get` は 2 行、`observation-analysis-must-trace-its-observation-time` は 1 行）。分類表 `.pair-agent/governance/skill-classification-20261103.tsv`（22d50d9）で照合すると active 46・project 13（うち 2 は live に残る保留、11 は移送済み）・archive 48 種。live `skills/`（HEAD）に無い名前は 59 種（archive 48 + project 11）。この 59 種は、最初の移動（19:27:47）より前の a72cb40^ の `skills/` に全部あった（`check_bug06_names.ps1` の実測: 存在 59・欠け 0）。読みの元は移動前の `skills/` なので、前に書いた「`skills/` 以外を読んだ」という推定は誤りとして撤回する。
- 前の作業の記録では使用ログを「1 行」と見ていた。実際は 108 行である。

## 再現手順

1. 本セッションで、スキル本文の `.md` を Read ツールで多数読む（分類・リンク検査の作業）。
2. `usage/skill-refs.jsonl` の末尾の行の時刻と session を見る。読みの時刻と同じ範囲の行が増えている。

## 影響（事実）

- この使用ログは、実際に使われた回数ではなく、読まれた回数を数えている。今の 108 行は本セッション内の読み出しだけで、対話での利用と作業中の読みを区別していない。
- TODO 12（参照ベースの自動淘汰）の入力が、このままでは作業中の読みで汚れる。

## 証拠

- `usage/skill-refs.jsonl` の 1〜108 行（上の時刻と session）。移した後は `usage/skill-refs.maintenance-20261103.jsonl`（対処を参照）。
- `tools/log_skill_ref.py`（記録）・`tools/skill_usage_rollup.py`（集計）。

## 対処

- 2026-11-03（直した。live master）:
  - `eea9462`: 参照ログの 1 行に、読み元の `cwd` と `agent_type` を足す（`tools/log_skill_ref.py`）。
  - `b3a42ed`: 同じ session の一括読み（10 秒内に 10 件以上。`--burst-n`・`--burst-sec` で変えられる）を、利用として数えない（`tools/skill_usage_rollup.py`）。除いた件数は stderr に `excluded_bulk` として出す。
- 本セッションの 108 行は、本番の `usage/skill-refs.jsonl` から `usage/skill-refs.maintenance-20261103.jsonl`（サイドカー・版管理しない）へ移した。本番は 0 バイトで始め直した。サイドカーは 108 行・16902 バイト・MD5 `CEDAD3A99E793B756E0A3E22C8D12B23`（移す前の本番と同じ MD5）。
- 試験: 記録と集計の試験 28 件すべて PASS（本番には書かず、サイドカーを読む写しで行った）。サイドカーの集計は `excluded_bulk=107`・`referenced=1`・`unmatched=0`・`malformed=0`・exit 0。残った 1 行は `a2a-proto-metadata-no-get`（18:43:12）。
- TODO 12 の入力は本番ログだけにする（サイドカーは入れない。推奨）。
- 未確認:
  - `cwd`・`agent_type` は本物のフック入力で確かめていない（試験は作った入力で行った）。
  - Bash の読みでフックが発火するかは未確認。
  - 18:43:12 の 1 行は TODO 3 の発火確認の読みと推定（未確認）。
  - 一括の原因（どの作業の読みか）は未確認。
  - 限界: 並列の利用で 10 秒内に 10 件以上読むと、それも除かれる（`skill_usage_rollup.py` の冒頭に明記）。
