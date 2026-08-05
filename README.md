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

## **スキルの横断収集（skill-survey）**

複数プロジェクトで蓄積されたスキルを横断収集・汎化するしくみです。**2つのモード**があります。

| モード | 出力先 | 汎化の実行者 | 使いどころ |
|---|---|---|---|
| **library**（既定） | `~/.claude/pair-agent/skill-library/pending/` | Python スクリプト（Haiku, 1件ずつ） | 定期的な棚卸し。差分だけ拾いたい |
| **harvest** | このリポジトリの `examples/skills/` | エージェントが全件を読んで汎化 | 全体を見渡して重複統合したい。リポジトリ資産として配布したい |

```
/skill-survey              # library モード（サーベイ + pending レビュー）
/skill-survey --review     # library モード（pending レビューのみ）
/skill-survey --harvest    # harvest モード（探索 → 汎化 → examples/skills/ へ取り込み）
```

harvest モードは、プロジェクト横断で全スキルを読んでから書くため、**1件ずつ処理する library モードにはできない工程**を担います。

- 複数プロジェクトに同名で存在するスキルの統合
- 病理が同じで切り口が違うスキルの1件化
- 「汎化すると意味が失われる」ものの除外（理由付き）
- `privateskills/` に置かれた非公開スキルの除外

取り込んだ結果は `skillimport.bat` でペア固有ライブラリへ配布します（前掲）。

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

## **スキルライブラリ（examples/skills/）**

`examples/skills/` には、複数プロジェクトのペアリングから生成・汎化されたグローバルスキルが 45 件収録されています。  
skill-survey が実際に何を出力するかを示す実例であり、そのままコピーして利用することもできます。

### ペアの働き方

| スキル | 内容 |
|---|---|
| `no-deferred-doubts.md` | 疑問はその場で追及する |
| `observation-scope-by-sufficiency.md` | 観察範囲は最大情報量で決める |
| `answer-before-editing.md` | 回答してから編集する（見切り発車で手を動かさない） |
| `working-code-over-clean-code.md` | 動くコードをきれいなコードより優先する |
| `web-lookup-before-using-libraries-apis.md` | ライブラリ・API使用前は必ずネットで最新を確認する |
| `product-framing-as-feature-filter.md` | プロダクトのフレーミングを機能追加の判定軸に使う |

### git・コミット運用

| スキル | 内容 |
|---|---|
| `process-git-autonomous.md` | git操作は確認なしで実行する |
| `process-commit-after-work.md` | 作業後はコミット・同期する |
| `solo-dev-merge-to-main-promptly.md` | 一人開発なら枝は main へ即合流してよい |
| `inbox-files-always-commit.md` | inbox ファイルは文脈に関係なく常にコミットする |

### テスト・検証

| スキル | 内容 |
|---|---|
| `process-tdd.md` | TDDで設計・実装・動作確認まで行う |
| `eval-by-tests-only.md` | テスト通過をコード評価の基準とする |
| `test-count-decrease-signals-degradation.md` | テスト総数の減少はデグレードのサイン |
| `test-inject-time-not-wall-clock.md` | 時刻の前後関係を検証するテストは時刻を明示注入する |
| `e2e-temp-datadir-with-cache-junction.md` | E2E は一時データディレクトリ＋キャッシュのジャンクション共有で |
| `gui-headless-screenshot-verification.md` | GUI の見た目はヘッドレスブラウザで自分で撮って確認する |

### 配線漏れ・経路の腐り

| スキル | 内容 |
|---|---|
| `count-registration-points-not-the-checklist.md` | 能力を足したら登録点を数えて潰す（チェックリストを信じない） |
| `llm-capability-two-outlets.md` | LLM に能力を「渡す」経路と「見せる」経路は別 |
| `stale-init-in-the-old-execution-path.md` | 実行経路を移したら旧経路の初期化と残骸を両方向で洗う |
| `fixed-but-nothing-changed-suspect-stale-process.md` | 「直したのに変わらない」ときは稼働プロセスの起動時刻を見る |
| `verify-you-are-in-the-real-environment.md` | 環境起因と診断する前に「その環境は実運用か」を確認する |

### LLM アプリの設計

| スキル | 内容 |
|---|---|
| `llm-output-stochasticity.md` | LLM出力の確率的性質を前提に設計する |
| `llm-judgment-tuned-by-vocabulary.md` | LLM 駆動の判定はプロンプトの一語で偏る |
| `tool-dispatch-bind-args-to-signature.md` | ツール dispatch はモデル引数を関数シグネチャに束縛する |
| `verification-models-by-role.md` | 検証モデルは役割別に選ぶ（回転／穴探査／交差検証） |
| `tool-module-three-layer-design.md` | ツールモジュールは「純粋整形 / I-O / 登録」の3層で書く |

### 層状アーキテクチャ

| スキル | 内容 |
|---|---|
| `layer-by-layer-completion.md` | レイヤは内側から一つずつ完成させる |
| `one-file-per-layer.md` | 各層は1ファイル |
| `per-layer-touchable-cli.md` | 各層に「触れる」最小CLIを用意する |
| `environment-grounding-is-caller-concern.md` | 環境の文脈は行動ループ層でなく呼び出し側が与える |
| `observability-at-composition-seams.md` | 観測点は層に埋めず合成点で外から包んで注入する |
| `responsibility-minimization.md` | 責務最小化 |

### 取り込み・ベンダリング

| スキル | 内容 |
|---|---|
| `vendoring-keeps-proven-code-coexisting.md` | 上流取り込みは既存の実証済みコードを消さず共存させる |
| `vendored-copy-diverges-both-ways.md` | ベンダリングしたコピーは双方向に乖離する |
| `transform-rules-grow-one-module-at-a-time.md` | 取り込み変換ルールは1モジュールずつ漸進的に育てる |
| `neutralize-code-lines-with-pass-not-comment.md` | Python の行を無効化するときは pass 置換 |

### データ・ドキュメント・運用

| スキル | 内容 |
|---|---|
| `schema-version-matches-migration-table.md` | スキーマバージョンとマイグレーション表の整合をテストで固定 |
| `no-physical-delete-use-logical-invalidation.md` | 履歴が価値を持つデータは物理削除せず論理無効化する |
| `keep-core-docs-in-sync.md` | 中核ドキュメント3点は実装と同期し続ける |
| `user-tunable-rules-in-editable-policy-doc.md` | ユーザーが調整する挙動ルールは編集可能なポリシー文書に置く |
| `lifecycle-features-as-hook-plugins.md` | ライフサイクルに絡む新機能はコア無改変のフックプラグインで |
| `cross-pollinate-improvements-both-ways.md` | 姉妹アプリの改善は双方向に横展開する |

### 環境（Windows / Python）

| スキル | 内容 |
|---|---|
| `scratch-dir-python-venv.md` | 作業ディレクトリのPythonにはvenvを使う |
| `windows-debug-output-cp932-safe.md` | Windows のデバッグ出力は cp932 安全に書く |
| `persistent-shell-driving-needs-sync-formatting.md` | 永続シェル駆動では出力を同期文字列化する |

### ペア固有ライブラリへの取り込み

`skillimport.bat` で `examples/skills/*.md` を `~/.claude/pair-agent/skills/`（および Antigravity 側）へ配ります。

```batch
skillimport.bat --list     :: 何が入るかの下見。何も書かない
skillimport.bat            :: 未導入のものだけ取り込む（既存ファイルは保護）
skillimport.bat --force    :: 既存も上書きする
```

> [!IMPORTANT]
> 既定では**既存ファイルを上書きしません**。配布先には師匠自身が育てたスキルが同居しているためです。  
> まず `--list` で差分を確認してから実行してください。

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
