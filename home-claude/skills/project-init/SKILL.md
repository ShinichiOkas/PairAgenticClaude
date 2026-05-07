---
name: project-init
description: プロジェクトに .pair-agent/ が存在しないとき、作業ディレクトリを初期化するスキル。project-start-existing から呼ばれるか、セッション開始チェックで自動発動する。
---

# プロジェクト作業ディレクトリの初期化

## 発動条件

セッション開始時に以下が両方とも成立する場合:
- 現在のプロジェクトに既存ファイルが存在する（完全な空ではない）
- `.pair-agent/` ディレクトリが存在しない

## 手順

1. 師匠に確認を求める:

   > `.pair-agent/` がありません。  
   > Pair Agent の作業ディレクトリを初期化してよいですか？  
   > （`agreements/`, `sprints/`, `skills/`, `current-sprint.json` が作成されます）

2. 承認されたら `~/.claude/pair-agent/template/` の内容をカレントディレクトリの `.pair-agent/` へコピーする。

3. `current-sprint.json` の `created_at` フィールドを現在の ISO 8601 日時で設定する。

4. 完了を報告する:

   > `.pair-agent/` を初期化しました。  
   > `.gitignore` に `.pair-agent/current-sprint.json` を追加することをお勧めします。

## 注意

- 師匠に確認せずに勝手に作成しない
- `.pair-agent/` がすでに存在する場合はこのスキルを発動しない
- 空ディレクトリ（`project-start-empty` の管轄）では発動しない。  
  空プロジェクトでは、プロジェクト方向が決まったタイミングで師匠の承認を得てから初期化する
- テンプレートが `~/.claude/pair-agent/template/` に見つからない場合は  
  「`install.sh`（または `install.bat`）を再実行してください」と案内する
