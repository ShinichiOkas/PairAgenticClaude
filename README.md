# Pair Agent for Claude Code & Google Antigravity

AIは何も知らない新入りとして始まり、師匠（あなた）が少しずつ任せながら育てていく  
――従来のAIエージェントとはまったく異なる前提で動く、エージェント用設定一式。

## 概要

Pair Agentは、`CLAUDE.md` / `GEMINI.md`・Skills・Rulesを組み合わせて、  
Claude Code や Google Antigravity (GeminiCLI) の上に「徒弟制度」を実現するものです。

### ファイル配置の設計思想

| 何を | どこに | 備考 |
|------|--------|------|
| Pair Agentの振る舞い定義 | `~/.claude/` または `~/.gemini/antigravity/` | どのプロジェクトでもPair Agentとして動く |
| 師匠の判断基準・用語・好み | `~/.../pair-agent/skills/` | ペア固有の長期資産。プロジェクトを跨ぐ |
| ビジョン記録 | `~/.../pair-agent/vision/` | 師匠の思考パターン。プロジェクトを跨ぐ |
| 叱責・修正記録 | `~/.../pair-agent/corrections/` | 境界線はペア固有 |
| プロジェクト初期化テンプレート | `~/.../pair-agent/template/` | `project-init` スキルが使用。リポジトリ不要 |
| 合意ドキュメント | `<project>/.pair-agent/agreements/` | スプリントはプロジェクトに紐づく |
| スプリント状態 | `<project>/.pair-agent/current-sprint.json` | プロジェクト単位の作業状態 |
| プロジェクト固有Skill | `<project>/.pair-agent/skills/` | そのプロジェクトだけの技術知見 (Claude用) |
| プロジェクト固有Skill | `<project>/.agents/skills/` | そのプロジェクトだけの技術知見 (Antigravity用) |

## インストール

### macOS / Linux  
```bash  
chmod +x install.sh  
./install.sh
```

### Windows  
```batch
.\install.bat
```

既存の `CLAUDE.md` がある場合はバックアップを作成し、Antigravity用に `GEMINI.md` も作成します。

## **プロジェクトへの導入**

> [!NOTE]
> **プロジェクトへの導入は自動化されています。**  
> インストール後に既存プロジェクトでエージェントを起動すると、`.pair-agent/` が存在しない場合に
> `project-init` スキルが自動的に初期化を提案します。

手動で初期化したい場合:

#### macOS / Linux
```bash
cd your-project  
./install.sh --project
```

#### Windows
```batch
cd your-project
path\to\install.bat --project
```

## **使い方**

インストール後、いつも通り `claude` または `geminicli` (Antigravity) を起動するだけです。  
 Pair Agentが自動的に有効になります。

### **最初のセッション**

- **空ディレクトリ**: 「何を作りたいですか？」と聞かれます。
- **既存プロジェクト（`.pair-agent/` なし）**: 作業ディレクトリの初期化を自動的に提案します。
- **既存プロジェクト（`.pair-agent/` あり）**: 進行中のスプリントがあれば状態を報告します。

### **スプリントの流れ**

1. ゴールを伝える → 協議フェーズ（合意ドキュメントを共同起草）  
2. 合意する → 実行フェーズ（AIが自律的に実装）  
3. 完了する → 振り返りフェーズ（ビジョン記録・Skill提案）

### **育て方**

* ルールを宣言する → 即座にconfirmed Skillとして記録される  
* 叱る → 境界線として記録され、次回から自発的に確認される  
* 用語を定義する → vocabulary Skillとして記録される  
* 繰り返し同じパターンが出る → AIがSkill昇格を提案する

## **スキルライブラリ（skill-survey）**

複数プロジェクトで蓄積されたスキルを横断収集・汎化してライブラリ化するツールです。

### セットアップ

インストール後、スキャン対象のプロジェクト親ディレクトリを設定します:

```json
// ~/.claude/pair-agent/skill-survey-config.json
{
  "project_roots": ["~/work/develop"],   // ← ここに追加
  "max_depth": 2,
  "model": "claude-haiku-4-5-20251001",
  "also_survey_global": true
}
```

APIキーは環境変数 `ANTHROPIC_API_KEY` か、プロジェクトルートの `.env` に記述します:

```
ANTHROPIC_API_KEY=sk-ant-...
```

### サーベイ実行

```bash
# macOS / Linux
python ~/.claude/pair-agent/tools/skill-survey.py

# Windows
python %USERPROFILE%\.claude\pair-agent\tools\skill-survey.py
```

各プロジェクトの `.pair-agent/skills/` とグローバルの `~/.claude/pair-agent/skills/` を走査し、
Claude APIでプロジェクト固有情報を検出・除去した汎化版を `~/.claude/pair-agent/skill-library/pending/` に出力します。

### レビュー

Claude Code 上で:

```
/skill-survey --review
```

pending のスキルが1件ずつ提示されます。各スキルに対して:

| 操作 | 結果 |
|------|------|
| approve | `approved/` に移動。グローバルスキルへの昇格を提案 |
| reject | 削除 |
| edit | その場で修正してから再提示 |
| skip | 今回はスキップ（pending に残る） |

### ライブラリの構造

```
~/.claude/pair-agent/skill-library/
├── index.md                    # 全エントリのカタログ
├── pending/                    # 汎化済み・承認待ち
├── approved/                   # 承認済み
└── survey-report-YYYY-MM-DD.md # サーベイ実行レポート
```

## **サンプルスキル**

`examples/skills/` には、本プロジェクト自体のペアリングから生成・昇格したグローバルスキルが収録されています。  
skill-survey が実際に何を出力するかを示す実例であり、そのままコピーして利用することもできます。

```
examples/
└── skills/
    ├── eval-by-tests-only.md           # テスト通過をコード評価の基準とする
    ├── llm-output-stochasticity.md     # LLM出力の確率的性質を前提に設計する
    ├── no-deferred-doubts.md           # 疑問はその場で追及する
    ├── observation-scope-by-sufficiency.md  # 観察範囲は最大情報量で決める
    ├── process-commit-after-work.md    # 作業後はコミット・同期する
    ├── process-git-autonomous.md       # git操作は確認なしで実行する
    ├── process-tdd.md                  # TDDで設計・実装・動作確認まで行う
    ├── scratch-dir-python-venv.md      # 作業ディレクトリのPythonにはvenvを使う
    └── working-code-over-clean-code.md # 動くコードをきれいなコードより優先する
```

## **アンインストール**

### macOS / Linux
```bash
./install.sh --uninstall
```

### Windows
```batch
.\install.bat --uninstall
```

`~/.claude/pair-agent/` の学習データは保持されます。  
 完全削除する場合は手動で `rm -rf ~/.claude/pair-agent/` を実行してください。
