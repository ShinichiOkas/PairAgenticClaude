---  
name: sprint-lifecycle  
description: スプリントのライフサイクル管理。新しいタスクを始める、スプリントの状態を遷移させる、完了処理をするときに使用する。「始めましょう」「これ完了」「状況は？」などの発話で発動。  
---

# スプリントライフサイクル管理

## 状態遷移

協議(deliberating) → 合意(agreed) → 実行(executing) → 振り返り(retrospecting) → 完了(completed)

差し戻しは実行中にいつでも可能（協議に戻る）。

## スプリント開始

**現在地は作業ツリーごと**（2026-09-21〜。旧・単一 `.pair-agent/current-sprint.json` は廃止・道標のみ。
詳細は対象プロジェクトの `CLAUDE.md`「スプリントの現在地は作業ツリーごと」を見る）。

### 旧形式からの移設（初回セッションで行う）

`.pair-agent/current-sprint.json` が**あり**、`.pair-agent/current/` が**無い**プロジェクトでは、
新方式へまだ移設されていない。セッション開始時にそのプロジェクトへ最初に触れる回で移設する:

1. `.pair-agent/current-sprint.json` の中身（経過含む）を丸ごと
   `.pair-agent/sprints/<sprint_id>.json` へ写す（`sprint_id` が無ければゴールから採番する）
2. 作業ツリーの鍵を計算し（下記コマンド）、`.pair-agent/current/<鍵>-<末尾ディレクトリ名>.json` を
   ポインタとして新規作成する（`journal` に手順 1 のファイルを指す）
3. `.pair-agent/current-sprint.json` を道標に置き換える:
```json
{
  "_moved": "現在地は .pair-agent/current/<鍵>.json（作業ツリーごと）、経過は .pair-agent/sprints/<sprint_id>.json。CLAUDE.md『スプリントの現在地は作業ツリーごと』を読むこと",
  "status": "moved"
}
```
4. 以降は下記の通常手順に従う

師匠がゴールを伝えたら:

1. 作業ツリーの鍵を計算する（`ホスト名 + git rev-parse --show-toplevel` の SHA-1 先頭 8 桁）
2. `.pair-agent/sprints/<sprint_id>.json` を新規作成し、経過（`経過` 配列）を書く先とする:
```json
{
  "sprint_id": "<uuid>",
  "status": "deliberating",
  "goal": "<ゴール>",
  "created_at": "<timestamp>",
  "agreement_path": ".pair-agent/agreements/<goal-slug>.md"
}
```
3. `.pair-agent/current/<鍵>-<末尾ディレクトリ名>.json` をポインタとして作成（無ければ新規、あれば上書き）:
```json
{
  "workcopy": { "host": "<host>", "path": "<top>", "key": "<鍵>" },
  "sprint_id": "<uuid>",
  "status": "deliberating",
  "journal": ".pair-agent/sprints/<sprint_id>.json",
  "updated_at": "<timestamp>"
}
```
4. 合意ドキュメントの起草を開始（/agreement-document を使用）

## **協議フェーズ**

`~/.claude/pair-agent/skills/` と `.pair-agent/skills/` からSkillを検索し協議深度を決定する:

* thorough: 不明点をすべて確認  
* light: 要点だけ確認  
* skip: 信頼して進む

師匠の選択肢:

* 懸念を受け入れてドキュメントを更新する  
* 見切り発車を宣言する（懸念をドキュメントに残して実行へ）

## **合意→実行**

師匠が「これでいこう」「OK」「始めて」等と言ったとき:

1. ジャーナル（`.pair-agent/sprints/<sprint_id>.json`・正）とポインタ（`.pair-agent/current/<鍵>-*.json`）
   両方の status を “executing” に更新
2. 合意ドキュメントの status を “executing” に更新  
3. 実行を開始

## **実行フェーズ**

* 合意ドキュメントのスコープ内で自律実行する  
* スコープはファイルパスで事前定義しない。タスク記述から判断する  
* 判断が難しい変更はその都度確認する  
* 「勝手なことするな」と言われたら即停止し、合意ドキュメントに追記する

### **差し戻し（人間・AIどちらも可）**

* 前提崩壊: 実装してみたら前提が間違っていた  
* より良い方法: 合意範囲を変えると全体最適になる

差し戻し後: ジャーナルとポインタ両方の status を “deliberating” に戻す。

## **完了→振り返り**

タスク完了時:

1. `.pair-agent/sprints/<sprint_id>.json`（ジャーナル。正）と `.pair-agent/current/<鍵>-*.json`
   （ポインタ）両方の status を “retrospecting” に更新
2. 「振り返りますか？」と問いかける  
3. 師匠の回答に応じて振り返り実施 or 先送り

振り返り完了後:

1. ジャーナルとポインタ両方の status を “completed” に更新（食い違ったらジャーナルを正とし
   ポインタを直す）。経過はすでに `.pair-agent/sprints/<sprint_id>.json` に書かれているので、
   改めて保存する操作は無い
2. 次のスプリントが始まるまでポインタは completed の sprint_id を指したまま残ってよい
   （D-3: 次の開始時にポインタの `journal` を新しいジャーナルへ書き換える）
