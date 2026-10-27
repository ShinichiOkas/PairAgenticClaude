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

1. 1 行告げて、そのまま初期化する（追加だけで git で戻せる。応答を待たない。2026-10-27 改め: 師匠の宣言『とにかく速度！回転！不停止！』『ユーザーの応答待ちは悪！』。旧: 師匠に確認を求める）:

   > `.pair-agent/` がありません。Pair Agent の作業ディレクトリを初期化します。  
   > （`agreements/`, `sprints/`, `acceptance/`, `assurance/`, `skills/`, `current/` が作成されます。要らなければ言ってください、戻します）

2. 以下の手順で初期化を実行する:
   - テンプレートの内容を `.pair-agent/` へコピーする
     - 優先パス: `~/.claude/pair-agent/template/` または `~/.gemini/config/pair-agent/template/`
   - `.agents/skills/`, `.agents/agents/`, `.agents/workflows/` を作成する（Antigravity 用。install の `--project` と同じ）
   - `CLAUDE.md` が存在し、`GEMINI.md` が存在しない場合、`CLAUDE.md` を `GEMINI.md` にコピーする
   - 作業ツリーの鍵を計算し（`ホスト名 + git rev-parse --show-toplevel` の SHA-1 先頭 8 桁）、
     `.pair-agent/current/<鍵>-<末尾ディレクトリ名>.json` に `status: "idle"` のポインタを作成する

3. 完了を報告する:

   > `.pair-agent/` を初期化しました。
   > （Antigravity用に `GEMINI.md` も作成しました）
   > 現在地は作業ツリーごとに `.pair-agent/current/` で管理されます（`.gitignore` は不要です）。

## 注意

- 既存ファイルは上書きしない（追加だけ）。初期化は告げて即実行し、師匠に止められたら戻す
- `.pair-agent/` がすでに存在する場合はこのスキルを発動しない
- 空ディレクトリ（`project-start-empty` の管轄）では発動しない。  
  空プロジェクトでは、プロジェクト方向が決まったタイミングで告げて初期化する
- テンプレートがユーザーホームに見つからない場合は  
  「`install.sh`（または `install.bat`）を再実行してください」と案内する

## 武器（スクリプト）

この Skill 専用の決定性スクリプト（Skill のディレクトリ基準）。機械にできる部分はこれに任せ、判断だけを自分でする。

- `scripts/init_project.py` — テンプレートのコピー・`.agents/` 配下の作成・GEMINI.md の複製・作業ツリーの鍵を使った idle ポインタの作成を一括で行う（追加だけ。既存は上書きしない。`.pair-agent/` 既存・空ディレクトリでは何もしない）。既定は下見、`--apply` で書く ／ 使い方: `python scripts/init_project.py --help`
