# バグ票: PC 間のマスターのマージ（gitmerge.resolve_file）は、片側で消した節を黙って落とせる

- 起票: 2026-11-23（票 2026-11-23-upstream-core-rules-lost-local-blocks-in-pamgr-6378f12 を直す中で見た）
- 状態: open

## 見たこと（症状と実測だけ）

- 7eae877 で、点検（`sweep._file`）の取り込み・節のマージがマスターの段落を消すときは J2 に止めるようにした
- `manager/pamgr/gitmerge.py` の `resolve_file` は、git でぶつかった `.md` を `sweep.merge_sections` で解き、結果をそのまま書いてコミットする。消える段落を数える手（`sections.lost_blocks`）は通っていない。`merge_sections` は、共通の元の版と同じ中身の節が片側で消えていれば、その節を落とす（`dropped`）
- 同じく、規範の文書でないファイル（スキルなど）の点検の自動の取り込み（adopt）は、消える段落を数えていない

## 再現手順

1. 2 つの clone の片方で、規範の文書の節を 1 つ消してコミットし、もう片方で同じファイルの別の節を書き換えてコミットする（git では同じファイルがぶつかる形にする）
2. 後の側で点検を走らせ、`gitsync.pull_step` → `gitmerge.merge_upstream` を通す
