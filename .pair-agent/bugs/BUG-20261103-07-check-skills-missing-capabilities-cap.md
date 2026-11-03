# BUG-20261103-07: tools/check_skills.py が skills/capabilities.cap の不在で落ちる

- 起票日: 2026-11-03
- 状態: fixed（2026-11-03・live master の `f3bc532`。検査本体の正常系は PairAgenticClaude 側でのみ走る。対処は「## 対処」）
- 重要度: 中（検査ツールが検査結果を出さずに終了する）
- 分類: 検査ツール / 欠陥
- 発見の経緯: BUG-20261103-06 の検証で live の検査ツールを確かめたとき。BUG-06 の範囲外（別件として記録）
- 対象: live `C:\Users\0000950207\.claude\pair-agent`（master・b3a42ed 時点）の `tools/check_skills.py`

## 症状・実測（2026-11-03。見たことだけ）

- `python -B tools/check_skills.py` を live の作業ツリーで実行すると、検査結果は表示されず、トレースバックの後に exit 1 で終わる。
- トレースバックの要点（原文のまま）:
  - `File "C:\Users\0000950207\.claude\pair-agent\tools\check_skills.py", line 420, in <module>` → `sys.exit(main())`
  - `File "...\tools\check_skills.py", line 244, in main` → `caps, other = parse_cap(CAP_FILE)`
  - `File "...\tools\check_skills.py", line 52, in parse_cap` → `for raw in path.read_text(encoding="utf-8").splitlines():`
  - `FileNotFoundError: [Errno 2] No such file or directory: 'C:\\Users\\0000950207\\.claude\\pair-agent\\skills\\capabilities.cap'`

## 再現手順

1. live（ブランチ master・作業ツリーは clean）で、`skills/capabilities.cap` が無いことを確かめる。
2. `python -B tools/check_skills.py` を実行する。exit 1 とトレースバックが出る。

## 証拠

- `git log --all -- skills/capabilities.cap` は空（このファイルは一度もコミットされていない）。
- `git show --stat eea9462 b3a42ed` に `tools/check_skills.py` の変更は無い（変わったのは `tools/log_skill_ref.py` と `tools/skill_usage_rollup.py`）。

## 対処

- 2026-11-03（直した。live master の `f3bc532`。変えたのは `tools/check_skills.py` の 1 ファイル・10 行追加）:
  - 直し方: `main()` の先頭で `CAP_FILE`（`skills/capabilities.cap`）が無いとき、トレースバックを出さず、無いことと理由を 3 行で stderr に出して `return 2` で止まる。
  - 直した後の live での実測（`python -B tools/check_skills.py`）: stderr に 3 行（「skill カタログの検査を実行できない（入力が無い）」・カタログのパス・PairAgenticClaude 側で実行する旨）。トレースバック無し。exit 2。
  - 同じツールの正常系（カタログがある PairAgenticClaude の作業ツリー）: `## 検査結果 ⭕ 問題 0 件`、exit 0。
  - 設計の選び方（推奨として採った）: 検査の入力（`skills/capabilities.cap` など）は PairAgenticClaude にある。live にカタログを写すと、後の判定で古くなる 2 つ目の複製になる。入力が無いのに空で通すと「問題 0 件」の偽の合格になる。だから、入力が無いことを言って止まる。
  - 未確認・限界: live では正常系の検査本体を走らせていない（入力が無いため。設計どおり）。修正前の実測（トレースバック・exit 1）は「症状・実測」の節のとおり。
