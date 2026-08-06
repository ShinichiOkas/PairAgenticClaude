---
name: 稼働中のアプリに pip install -e を実行しない
description: アプリ稼働中に同じ venv へ editable install を上書きすると console_scripts の .exe 書込に失敗して半壊しうる（本体 import すら不可）。停止後に行うか、失敗したら再実行で復旧する
type: domain
maturity: draft
---

新パッケージを取り込んだ後の venv 同期などで `pip install -e .` を**そのアプリの稼働中に実行すると、editable install が半壊しうる**（Windows での観測）。`WARNING: Failed to write executable - trying to use .deleteme logic` が出て、旧登録を消した後の新規書込に失敗し、パッケージ本体の `import` すら不可になる。

**Why:** 実際にフルスイート実行前の venv 同期を稼働中に行って editable install が破損し、テストが収集エラーで全滅した。**再試行**で `.deleteme` 経由の書込に成功して復旧し、残った不正配布（`~xxx` 形式の dist-info）を掃除して `pip check` クリーンに戻した。ロックの主が何か（アプリ本体・AV スキャン・別プロセスの .exe）は特定できておらず、**原因を断定せず観測した失敗モードと対処だけを残す**。

**How to apply:**
- パッケージ追加後の venv 同期（`pip install -e .`）は、できればアプリ・常駐コンパニオンを**停止してから**行う
- 稼働中に実行して `Failed to write executable` が出たら、慌てず**もう一度実行**する（`.deleteme` 経由で復旧しうる）。復旧後は `import <pkg>` と `pip check`、`~` 始まりの不正 dist-info の掃除を確認する
- editable が半壊すると import 不可でテスト全滅に見えるが、**環境問題でありコードの回帰ではない**。慌てて他をいじらない
- `--no-deps` は依存解決を省くだけで .exe 書込問題は避けられない
- 関連: [[verify-you-are-in-the-real-environment]] / [[fixed-but-nothing-changed-suspect-stale-process]]
