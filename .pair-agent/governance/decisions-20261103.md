# 仕分けの判断記録（2026-11-03・TODO 8）

- 対象: 分類表 `skill-classification-20261103.tsv`（22d50d9）の 648 件（active 244・project 66・archive 338）
- 規則: `skill-classification-rules-20261103.md`（22d50d9）
- 確認: advisor（TODO 8 の gate）。判定は「表どおり進めてよい」。移動は `git mv` のため可逆。

## 1. 最初に見てほしい点: 宣言例外が active の過半を支えている

- active 244 件のうち、reason が「宣言」「師匠」に依る行は **129 件**（過半）。
- 規則では、師匠が宣言した普遍的な規則は 1 事例でも active にできる（信頼度 mid）。129 件はこの例外に依る。
- 129 件から seed 20261103 で無作為に抽出した 20 件（`sample-declared-active-20261103.txt`）を読んだ。本文に師匠の発話を引用しているのは **2 件**（responsibility-minimization・verification-plan）のみ。残り 18 件は「宣言あり」「原文あり」と書くだけで、原文は表に入っていない。
- 20 件のうち **5 件**は単一事例（1 文脈・事例 1 件）で例外を適用している。
- 判断を求める点（ユーザーだけが決められる）: 宣言の一文を、事例 1 件でも active にしてよいか。推奨: 今は表のまま残し、原文の確認と見直しは TODO 12 の参照データで行う。no なら 24 件（節 2）を archive へ寄せる。

## 2. 単一事例の cue 行 24 件（推奨: 残す）

- 定義（機械的）: active 行のうち reason に「事例1件」「事例は1件」「1文脈」「例外適用」「例外で可」「事例は1」「1件のため」「事例1」「単一」のいずれかを含む行。
- 内訳: mid 21・low 2・high 1。
- 一覧: `single-case-rows-20261103.tsv`（この commit に含む）。

## 2b. 個別に確認した行（cue の有無は問わない。表どおり残す）

- always-test-in-production（active mid）: 固有名（`~/.mnemo`・`check_production.py`・`deny_production.py`）を含む。規則の (a)（固有名を消しても成立）に照らすと要確認。
- no-deferred-doubts（active mid）: 宣言のみ。
- inbox-files-always-commit（active low）。
- timeclock-stays-human-not-agent（project・MSTenantMCP mid）: 師匠の「エージェントは代行しないならエージェントじゃない」の適用範囲が未決。
- answer-before-editing（archive mid）: 2026-10-27 の「推奨で即着手」と衝突するため archive に置いた。
- ambiguity-is-a-branch-not-an-error（project・LogicParser mid）。
- purpose-is-continuous-improvement-not-pass-fail（project・AgenticWorkspace mid）。
- independent-mcp-service-5-file-pattern（archive）: コードの雛形。
- 分類バッチ 01 の 3 行（行番号 5・49・51）: 一時ファイルでの番号のため、skill 名は TODO 14 の最終報告で挙げる。

## 3. リンクと移送の判断（項目 1〜5 は TODO 8 で推奨として決めた。項目 6 は TODO 11 で定めた）

1. 表は変えない（active 244・project 66・archive 338）。宣言例外は残す（節 1）。
2. 注目行は表どおり。再分類は行わない。
3. 非 active への参照（BUG-20261103-04）は、再分類ではなく機械的な書き換えで直す。`[[stem]]` を `` `stem` `` に変えた（7f7fff1・157 ファイル・359 箇所）。front matter は変えていない。
4. TODO 10 の push: 対象 repo ごとに、移すファイルだけを pathspec で stage してコミットする。その repo に先行の未 push コミットが無いときだけ push する。あれば local に残して報告する。他の変更はコミットしない。
5. サブモジュール参照（main の `external/pair-agent-skills`）は、ライブ clone を push するたびに更新する（一括にしない）。手順: `git -C external/pair-agent-skills fetch origin` → `checkout <sha>` → main で `git add external/pair-agent-skills`。1 バッチ = ライブと main の 2 コミット（どちらも push）。
6. リンクの解決判定（TODO 11・2026-11-03）。本文の `[[X]]` の X を次の順で見る。(a) live の `skills/` に X.md があれば残す（in-skills。active・保留のどちらも可）。(b) live の `corrections/`・`vision/`・`skill-library/` に X.* がある、またはハーネス `~/.claude/skills/X/SKILL.md` があれば残す（outside）。(c) どれも無ければ `` `X` `` に書き換える（unresolved）。`archive/` と `skills-backup-*` は解決に数えない。他リポジトリへ移したものも数えない。ハーネス由来の 4 名（`agreement-document`・`project-start-existing`・`skill-learning`・`vision-record`）は (b) で残す。計測は `tools/check_skill_links.py`（本文のみ。front matter・インラインコード・フェンスは対象外）。書き換え後の期待値は unresolved 0・outside 23・本文 552（629 − 77）。4bfe0d0（2026-11-02・「移送した固有 skill 9 件をペア固有から削除」）は TODO 10 の移送（1c8373e・afe0f6f、2026-11-03）とは別の commit として扱う。

## 4. TODO 10 の扱い（この記録で定める）

- 対象の `.pair-agent/skills/` に同名 stem の別内容のファイルがある場合: 上書きしない。そのファイルは移さずライブ clone に残し、報告する。
- project 行きのファイル本文には、pair-agent の stem への `[[リンク]]` が残っている。対象 repo の中では解決しない。対象 repo 内の書き換えは範囲外のため、そのまま残す。

## 5. 未完の事項

- TODO 12（参照ベースの自動淘汰）: 使用ログは 1 行のみ。データが貯まるまで blocked。
- BUG-20261102-03（二重管理）: open のまま。
- BUG-20261103-04: 対処済み（7f7fff1）。素の表記 10 箇所は、もともとリンクでない記述として残る。移動後の再検査は TODO 11 で行い、結果をバグ票に追記する。
