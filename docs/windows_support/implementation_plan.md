# 実装計画：プロジェクト初期化の自動化

## 背景・課題

現在 `install.bat --project` で手動コピーしている `.pair-agent/` の初期化を、  
Claude Code が自動的に行うスキルへ移行する。

また、テンプレートファイルを `~/.claude/pair-agent/template/` に格納することで、  
インストール後に元リポジトリが不要な完全自己完結型にする。

---

## 設計方針

### 1. テンプレートの格納先変更

| 変更前 | 変更後 |
|---|---|
| `project-template/.pair-agent/` (リポジトリ内) | `~/.claude/pair-agent/template/` (ユーザーホーム内) |

インストールスクリプト（`install.sh` / `install.bat`）が  
`project-template/.pair-agent/` の内容を `~/.claude/pair-agent/template/` にコピーする。  
インストール後はリポジトリが無くても動作する。

### 2. 新スキル `project-init` の追加

`~/.claude/skills/project-init/SKILL.md` を新規作成する。

**発動条件:**  
セッション開始時に `.pair-agent/` が存在しないことを検知したとき。

**動作:**  
1. `.pair-agent/` が存在しない既存プロジェクトを検知
2. 師匠に確認: 「`.pair-agent/` がありません。Pair Agent の作業ディレクトリを初期化しますか？」
3. 承認されたら `~/.claude/pair-agent/template/` の内容をコピー
4. `current-sprint.json` の `created_at` を現在時刻で初期化

**修正が必要なスキル:**  
- `project-start-existing`: `.pair-agent/` の不在チェックを `project-init` スキルに委譲するよう修正
- `project-start-empty`: `.pair-agent/` を即時作成するのではなく、  
  プロジェクト方向決定後に `project-init` スキルを呼ぶよう修正

### 3. `pair-agent-core.md` ルールの更新

セッション開始手順に「`.pair-agent/` が存在しなければ `project-init` スキルを実行する」を追加する。

---

## 変更ファイル一覧

### home-claude/（インストール元）

#### [NEW] `home-claude/skills/project-init/SKILL.md`
- `.pair-agent/` 不在検知・初期化スキル本体
- テンプレートのコピー手順を記述
- 承認フロー付き

#### [MODIFY] `home-claude/pair-agent/template/`（新規ディレクトリ）
- `project-template/.pair-agent/` の内容をこちらへ移動

#### [MODIFY] `home-claude/skills/project-start-existing/SKILL.md`
- `.pair-agent/` 不在時は `project-init` スキルへ委譲する記述を追加

#### [MODIFY] `home-claude/rules/pair-agent-core.md`
- セッション開始手順に `.pair-agent/` 不在チェックを追加

### インストールスクリプト

#### [MODIFY] `install.sh`
- `project-template/.pair-agent/` を `~/.claude/pair-agent/template/` にコピーするステップを追加
- `--project` オプションの動作を  
  「リポジトリからのコピー」→「`~/.claude/pair-agent/template/` からのコピー」に変更

#### [MODIFY] `install.bat`
- 同上（Windows版）

---

## 検証計画

1. `install.sh` / `install.bat` を実行し、`~/.claude/pair-agent/template/` が正しく作成されることを確認
2. `.pair-agent/` なしのプロジェクトで claude を起動し、自動的に初期化の確認が表示されることを確認
3. 承認後に `.pair-agent/` ディレクトリ構造が正しく作成されることを確認
4. `--project` フラグが廃止されてもドキュメントが正しく更新されることを確認

---

## 備考

> [!NOTE]
> `--project` オプションは互換性のために残しつつ、動作を  
> `~/.claude/pair-agent/template/` からのコピーに変更する。  
> 将来的には「スキルで自動化されたので不要です」とドキュメントに記載できる。
