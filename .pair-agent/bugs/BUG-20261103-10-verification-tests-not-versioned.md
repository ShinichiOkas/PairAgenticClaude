# BUG-20261103-10: BUG-06・08 の検証テストが、どの repo にも commit されていない

- 起票日: 2026-11-03（2026-11-04 に再確認）
- 状態: fixed（2026-11-04・live master の 7aedb6e。検証は「## 対処」）
- 重要度: 中（BUG-08 の票は、この検証テストの結果を根拠に「直し済み」と記録している〈票の 62 行〉。テストが version 管理に無いため、後の変更で同じ不具合が戻っても検出されない）
- 分類: 検証の再現性
- 対象: live `C:\Users\0000950207\.claude\pair-agent\tools\`（テストの対象: `log_skill_ref.py`・`skill_usage_rollup.py`）

## 症状・実測（見たことだけ）

- 検証テストは scratchpad にだけ在り、どの git repo にも入っていない。
  - `C:\Users\000095~1\AppData\Local\Temp\claude\778e87595a7d3e63\0e4ebe9b-f99a-4cc5-bcdc-a7888f59db43\scratchpad\test_skill_ref.py`（計装フック）
  - 同じ scratchpad の `test_bug06_sidecar.py`（BUG-06 の集計。サイドカーを読み、本体の rollup を複製している）
  - 同じ scratchpad の `bug08\test_bug08.py`（BUG-08 の保守の読みの除外）
  - 同じ scratchpad の `test_bug06.py`（古い版。本番ログが空のため FAIL する）
  - live の `tools\` にテストは無い。main の `tests/` には BUG-06・07・08 のテストは無い。
- 実行結果（保存先 `...\scratchpad\final3\`）:
  - `test_skill_ref.py`: TOTAL 23・FAILED 0・exit 0
  - `test_bug06_sidecar.py`: RESULT: ALL PASS・exit 0
  - `bug08\test_bug08.py`: TOTAL 38・FAILED 0・exit 0
  - `test_bug06.py`: RESULT: FAIL 2・exit 1（`excluded=0 (want 107)`。本番ログが空なので、この版は前提が合わない）
- BUG-08 の票（`.pair-agent/bugs/BUG-20261103-08-maintenance-reads-counted-in-production.md` の 62 行）は、`test_bug08` 38/38・`test_skill_ref` 23/23・`test_bug06_sidecar`（サイドカーを読む複製）ALL PASS を、直したことの根拠に書いている。
- BUG-07（`check_skills` の capabilities 欠落）には検証テストが無い（scratchpad を探した限り無し）。
- 本番ログ `C:\Users\0000950207\.claude\pair-agent\usage\skill-refs.jsonl` は 0 バイト（MD5 d41d8cd9…・2026-11-04 に確認）。
- サイドカー `C:\Users\0000950207\.claude\pair-agent\usage\skill-refs.maintenance-20261103-08.jsonl` は 17 行（MD5 6957d297…・2026-11-04 に確認）。`test_bug06_sidecar.py` はこれを読む。

## 再現手順

1. 上の 3 ファイルを `python` で実行し、exit code と最終行（TOTAL / RESULT）を見る。
2. 本番ログのバイト数を確かめる（`stat -c %s`）。

## 影響（事実）

- テストが version 管理に無いため、`tools/log_skill_ref.py` と `tools/skill_usage_rollup.py` を変えたとき、BUG-06・08 の動作が戻っても検出する仕組みが無い。
- `test_bug06_sidecar.py` はサイドカー（session ID を含み、version 管理の対象外）を読むため、そのまま commit できない。

## 未確認

- テストの入力（フックの JSON の形・`cwd`・`agent_type`）が、実際のフック入力と一致するか（BUG-06 の票と同じ未確認）。
- BUG-07 の検証方法（票に記載なし）。

## 対処

- 2026-11-04: 直す役を並列で起こす（TODO 15）。方針（推奨で決めた）: 3 本を live の `tools/tests/` へ移し、入力は合成データ（一時ディレクトリ・`synth-0001` 形式の ID）にする。本番ログとサイドカーは読まない・commit しない。`test_bug06.py` は移さない。検査は弱めない。ツールのロジックは変えない。
- 2026-11-04: 直した（live `tools/tests/`・commit 7aedb6e・push 済み。main は db5622e で取り込んだ）。3 本: `test_skill_ref.py`・`test_bug06_sidecar.py`・`test_bug08.py`。
- 検証（2026-11-04・対話側が live の `tools/tests/` から 3 本を再実行し、exit code を実測）:
  - `test_skill_ref.py`: TOTAL 23・FAILED 0・exit 0
  - `test_bug06_sidecar.py`: RESULT ALL PASS・exit 0
  - `test_bug08.py`: TOTAL 38・FAILED 0・exit 0
- 本番ログとサイドカーは前後で変わらず（本番ログ 0 バイト・MD5 d41d8cd98f00b204e9800998ecf8427e。サイドカー 17 行・MD5 6957d297b35895722a2d47664b6345de）。新しいテストがこの 2 つと scratchpad を指していないことは grep で確認した（合成ルートと説明文だけ）。
- 感度（テストが壊れた実装を落とすか）は修正役の報告による。対話側では再実行していない。

## 証拠

- `...\scratchpad\final3\` の 4 ファイル（上の結果）
- 本番ログ 0 バイト（MD5 d41d8cd98f00b204e9800998ecf8427e）
- サイドカー 17 行（MD5 6957d297b35895722a2d47664b6345de）

## 訂正（2026-11-04）

- 「症状・実測」の 2 行（13 行・25 行）は誤り。
  - 13 行: 旧 `test_bug06_sidecar.py` は本体の rollup を複製していなかった。原本は `skill_usage_rollup.py` 本体を `--log` 付きで実行していた（原本の本文で確認）。
  - 25 行: 原本が読んでいたのは `-08` のサイドカー（17 行）ではなく、旧名 `usage/skill-refs.maintenance-20261103.jsonl`（16902 バイト・108 行）だった。
- 同じ誤り（「サイドカーを読む複製」）が BUG-08 の票 62 行にもあった。そちらも訂正した。
- 旧名のファイル（108 行）は live にまだ残っている。新しいテストは読まない。
