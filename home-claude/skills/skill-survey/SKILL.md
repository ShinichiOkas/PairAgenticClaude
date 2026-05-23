---
name: skill-survey
description: スキルライブラリのサーベイと対話レビュー。プロジェクト横断でスキルを収集・汎化し、pending スキルを師匠と一緒にレビューして approve/reject する。
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Skill Survey — スキルライブラリ管理

## 使い方

```
/skill-survey              # サーベイ実行 + pending レビュー
/skill-survey --review     # サーベイはスキップ、pending レビューのみ
/skill-survey --approve <slug>   # 特定スキルを直接 approve
/skill-survey --reject <slug>    # 特定スキルを直接 reject
```

## 手順

### 1. 起動時の判断

引数なし、または `--review` なし → サーベイを実行するか確認する:

> 「skill-survey スクリプトを実行してスキルを収集しますか？（既処理スキルはスキップされます）」

Yes → Phase 2 へ。No → Phase 3 へ。

### 2. サーベイ実行

```bash
python ~/.claude/pair-agent/tools/skill-survey.py
```

（スクリプトが見つからない場合は `python <PAIR_AGENT_REPO>/tools/skill-survey.py` を試す）

実行後、最新の `survey-report-<date>.md` を読んで結果を要約して師匠に伝える。

### 3. Pending スキルのレビュー

`~/.claude/pair-agent/skill-library/pending/` 内の `.md` ファイルを一覧表示する。

各スキルについて:
1. ファイルを読んで内容を師匠に提示（名前・スコア・汎化の要点・元プロジェクト）
2. 師匠に選択を求める:
   - **approve** → `approved/` に移動。`~/.claude/pair-agent/skills/` への昇格を提案（任意）
   - **reject** → `pending/` から削除。理由があれば記録
   - **edit** → 師匠の指示に従って内容を修正してから再提示
   - **skip** → 今回はスキップ（pending に残す）

複数ある場合は一件ずつ順番に処理する。

### 4. Approve 処理

`pending/<slug>.md` を `approved/<slug>.md` に移動する:
- フロントマターの `status: pending` → `status: approved` に変更
- `approved_date: <今日の日付>` を追加
- `~/.claude/pair-agent/skill-library/index.md` の該当行を更新（status を approved に）

昇格の提案:
> 「`~/.claude/pair-agent/skills/<slug>.md` としてグローバルスキルに昇格させますか？」

Yes → approved版をコピーし、survey metadata フィールド（source_project, source_path, survey_date, generalization_score, status）を削除した上で保存。

### 5. Reject 処理

- `pending/<slug>.md` を削除
- `.processed.json` には既にエントリがあるので再サーベイ対象にはならない
- 必要なら理由をメモとしてレポートに追記

### 6. 完了報告

> 「レビュー完了: approve X件 / reject Y件 / skip Z件」

---

## ライブラリ構造（参照用）

```
~/.claude/pair-agent/skill-library/
├── index.md                  # 全エントリカタログ
├── .processed.json           # 処理済みソースパス追跡
├── pending/                  # 承認待ち
│   └── <slug>.md
├── approved/                 # 承認済み
│   └── <slug>.md
└── survey-report-<date>.md   # サーベイレポート
```

## 設定ファイル

`~/.claude/pair-agent/skill-survey-config.json` でスキャン対象を管理:

```json
{
  "project_roots": ["~/work/develop"],
  "max_depth": 2,
  "output_dir": "~/.claude/pair-agent/skill-library",
  "model": "claude-haiku-4-5-20251001",
  "also_survey_global": true
}
```

プロジェクトを追加したときはこのファイルに追記する。
