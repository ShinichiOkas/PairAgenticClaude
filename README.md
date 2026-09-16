# Pair Agent for Claude Code & Google Antigravity

AIは何も知らない新入りとして始まり、師匠（あなた）が少しずつ任せながら育てていく  
――従来のAIエージェントとはまったく異なる前提で動く、エージェント用設定一式。

## 概要

Pair Agentは、`CLAUDE.md` / `GEMINI.md`・Skills・Rulesを組み合わせて、  
Claude Code や Google Antigravity (Gemini) の上に「徒弟制度」と「成果物因果マルチエージェント」を実現するものです。

### ファイル配置の設計思想

| 何を | どこに | 備考 |
|------|--------|------|
| Pair Agentの振る舞い定義 | `~/.claude/` または `~/.gemini/config/` | どのプロジェクトでもPair Agentとして動く |
| 師匠の判断基準・用語・好み | `~/.../pair-agent/skills/` | ペア固有の長期資産。プロジェクトを跨ぐ |
| ビジョン記録 | `~/.../pair-agent/vision/` | 師匠の思考パターン。プロジェクトを跨ぐ |
| 叱責・修正記録 | `~/.../pair-agent/corrections/` | 境界線はペア固有 |
| プロジェクト初期化テンプレート | `~/.../pair-agent/template/` | `project-init` スキルが使用。リポジトリ不要 |
| 合意ドキュメント | `<project>/.pair-agent/agreements/` | スプリントはプロジェクトに紐づく |
| スプリント状態 | `<project>/.pair-agent/current-sprint.json` | プロジェクト単位の作業状態 |
| プロジェクト固有Skill | `<project>/.pair-agent/skills/` | そのプロジェクトだけの技術知見 (Claude用) |
| プロジェクト固有Skill | `<project>/.agents/skills/` | そのプロジェクトだけの技術知見 (Antigravity用) |
| サブエージェント定義 | `.claude/agents/` / `.agents/agents/` | 特化役割エージェント仕様書 |
| ワークフロー定義 | `.claude/workflows/` / `.agents/workflows/` | 成果物DAG台本 (JS / JSON) |

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
path/to/PairAgenticClaude/install.sh --project
```

#### Windows
```batch
cd your-project
path\to\PairAgenticClaude\install.bat --project
```

## **使い方**

インストール後、いつも通り `claude` または `gemini` / `antigravity` を起動するだけです。  
Pair Agentが自動的に有効になります。

### **最初のセッション**

- **空ディレクトリ**: 「何を作りたいですか？」と聞かれます。
- **既存プロジェクト（`.pair-agent/` なし）**: 作業ディレクトリの初期化を自動的に提案します。
- **既存プロジェクト（`.pair-agent/` あり）**: 進行中のスプリントがあれば状態を報告します。

### **スプリントの流れ**

1. **協議フェーズ**: ゴールを伝える → 合意ドキュメントを共同起草し、適用するプロセスモデル（`.mk`）を選定
2. **合意フェーズ**: 完了条件・スコープ・成果物因果を確認し合意
3. **実行フェーズ**: マルチエージェント台本を駆動、またはサブエージェントに委譲（人間ゲートで適宜確認）
4. **振り返りフェーズ**: ビジョン記録・Skill提案・学びの蓄積

---

## **マルチエージェント／サブエージェント協調**

`AgentRoleDesign` の検討成果を取り込み、Claude Code と Google Antigravity (Gemini) の両方で、成果物因果定義（`.mk`）に基づくサブエージェント群を動作させることができます。

### 主エージェントとサブエージェントの役割分担

- **主エージェント（Pair Agent: 親）**: 師匠（ユーザー）との対話窓口。スプリントを管理し、人間ゲートで確認を求めます。
- **サブエージェント（役割エージェント: 子）**: 成果物因果グラフの単一 target に責任を負います。`deps` のみを読み、`blocks`（遮断対象）を見ずに作業し、事後条件を満たして REPORT を返します。主エージェントの対話規範はサブエージェントには適用されません。

### 1. マルチエージェント書式の一括出力 (`emit_agents.py`)

プロジェクト内の `models/*.mk` から、Claude Code および Google Antigravity の双方に対応したエージェント定義・スキルカタログ・ワークフロー定義を一括生成します。

```bash
# カレントディレクトリに全モデル（Claude & Gemini）を出力
python tools/emit_agents.py

# 特定モデルのみ Gemini 向けに出力
python tools/emit_agents.py models/waterfall-core.mk --target=gemini

# ユーザー環境にグローバル配備
python tools/emit_agents.py --dest=global
```

### 2. 成果物 DAG ワークフローの実行 (`run_workflow.py`)

定義された DAG に従って各段のエージェントを順次駆動します。

```bash
# 実行判定の確認 (dry-run)
python tools/run_workflow.py waterfall-core --dry-run

# ワークフローを実行（人間ゲートで一時停止）
python tools/run_workflow.py waterfall-core --root=.
```

- **起動の2条件 (P-53)**: 必須 dep が揃っているか、かつ deps が target より新しいか判定
- **H-8 機構**: 成果物内容が変わらなければ mtime を進めず、下流の無駄な空回りを防止
- **人間ゲート**: `gate: H1...` が指定された成果物は、師匠の判断を仰ぐため自動停止

詳細な仕様と運用方法は [docs/multi-agent-guide.md](docs/multi-agent-guide.md) を参照してください。

---

## **育て方**

* ルールを宣言する → 即座にconfirmed Skillとして記録される  
* 叱る・修正する → 即座にCorrectionRecordとして記録され、境界線を学ぶ  
* 振り返りを行う → ビジョン記録が蓄積され、Skillがdraftからconfirmedへ昇格する  

## **アンインストール**

```bash
./install.sh --uninstall
```
```batch
.\install.bat --uninstall
```
※ `pair-agent/` 配下に蓄積された学習データ（skills, vision, corrections）は保護されます。
