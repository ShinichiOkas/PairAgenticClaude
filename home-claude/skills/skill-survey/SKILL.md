---
name: skill-survey
description: スキルライブラリのサーベイと対話レビュー。プロジェクト横断でスキルを収集・汎化し、pending スキルを師匠と一緒にレビューして approve/reject する。リポジトリの examples/skills/ への取り込み（harvest）も担う。
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Skill Survey — スキルライブラリ管理

プロジェクト横断でスキルを収集し、汎化して再利用可能にする。**2つのモード**を持つ。

| モード | 出力先 | 汎化の実行者 | 使いどころ |
|---|---|---|---|
| **library**（既定） | `~/.claude/pair-agent/skill-library/pending/` | Python スクリプト（Haiku, 1件ずつ） | 定期的な棚卸し。件数が多い・逐次レビューしたい |
| **harvest** | Pair Agent リポジトリの `examples/skills/` | **私が直接読んで汎化** | リポジトリ資産として配布したい。重複統合・取捨選択の判断が要る |

## 使い方

```
/skill-survey              # library モード: サーベイ実行 + pending レビュー
/skill-survey --review     # library モード: サーベイはスキップ、pending レビューのみ
/skill-survey --approve <slug>   # 特定スキルを直接 approve
/skill-survey --reject <slug>    # 特定スキルを直接 reject
/skill-survey --harvest    # harvest モード: 探索 → 汎化 → examples/skills/ へ取り込み
```

引数なしで起動されたら、まず**どちらのモードか**を師匠に確認する。

---

# harvest モード — プロジェクト探索してリポジトリへ取り込む

## 1. 探索（何がどこにあるかを先に出す）

親ディレクトリ配下から、pair-agent を使っているプロジェクトを機械的に洗い出す:

```powershell
Get-ChildItem -Path <PROJECT_ROOT> -Directory | ForEach-Object {
  $p = Join-Path $_.FullName ".pair-agent\skills"
  $a = Join-Path $_.FullName ".agents\skills"
  if ((Test-Path $p) -or (Test-Path $a)) {
    Get-ChildItem -Path $p,$a -File -Recurse -ErrorAction SilentlyContinue |
      ForEach-Object { "{0,-20} {1,6}  {2}" -f $_.Directory.Parent.Parent.Name, $_.Length, $_.Name }
  }
}
```

`<PROJECT_ROOT>` は `~/.claude/pair-agent/skill-survey-config.json` の `project_roots` を使う。

**この段階で師匠に事実を報告する**:
- 何プロジェクトに何件あるか（`.gitkeep` のみのプロジェクトは除外して数える）
- 同名・同サイズのファイルが複数プロジェクトにあるか（＝既に横断展開されたスキル）
- 既に `examples/skills/` にある件数

## 2. 除外判定（読む前に落とすもの）

- `.gitkeep` / 空ファイル
- **`privateskills/` に同名ファイルがあるもの** — 師匠が意図的に非公開にしている。`examples/` は git 追跡されるので入れない
- `.agents/skills/` 配下でも、明らかに第三者由来（プロジェクトに同梱された外部スキル）のもの

## 3. 全件を自分で読む

`Read` で**全ファイルを読む**。並列に投げてよい。要約や grep で済ませない —— 汎化の判断は本文の細部（実際に踏んだ失敗・数値・コード例）に依存する。

## 4. 汎化判定

各スキルを4段階で判定する:

| 判定 | 基準 | 処理 |
|---|---|---|
| **high** | プロジェクト固有情報がほぼない。原則がそのまま他所で成立する | 汎化して取り込む |
| **medium** | 固有情報はあるが、汎化すれば十分に再利用可能 | 汎化して取り込む |
| **low** | 固有情報が根幹に絡み、汎化すると意味が失われる | 取り込まない（理由を報告） |
| **skip** | 一時メモ・空・既存と完全重複 | 取り込まない |

**low に落としやすいもの**: 特定製品の内部設計（ストア構成・独自データモデル）、特定 SaaS の認証手順、そのプロダクト固有のフェーズ名に紐づく残課題。

**逆に high に上げてよいもの**: 「実際に踏んだ壊れ方」が具体的に書かれているもの。固有名を外しても失敗の機序が残るなら価値は落ちない。

## 5. 汎化の方針

- 固有のプロジェクト名 → 概念説明に置換（`Mnemo で` → `この製品で` / `実際に`）
- 固有のパス・モジュール名 → 役割で言い換える（`core/topic_tree_hook.py` → `先行実装`）
- 固有の環境変数 → `{ENV_VAR_NAME}` または「データルートの環境変数」
- **本質的なルール・原則・実測値・コード例は保持する。** 削ると「もっともらしいが使えない一般論」になる
- **師匠の言葉（原文引用）は残す。** これが判断の根拠であり、Pair Agent の資産の中核
- フロントマターの `source_sprint_ids` / `source_project` / `provenance` の固有部分は削除。`name` / `description` / `type` / `maturity` は残す
- 出力形式は既存の `examples/skills/*.md` に揃える:

```markdown
---
name: <日本語の短い名前>
description: <一行>
type: process | feedback | domain | reference
maturity: confirmed | forming | draft
---

<ルール本文>

**Why:** <なぜそうするか。実際に踏んだ失敗を含める>

**How to apply:**
- <具体的な適用手順>
- 関連: [[other-skill-slug]]
```

## 6. 重複統合（スクリプトにはできない工程）

1件ずつ処理する library モードと違い、harvest では**全件を見渡してから**書く。

- **同名ファイルが複数プロジェクトにある** → 1件に統合する（内容差があれば新しい方／詳しい方を採る）
- **病理が同じで切り口が違う複数スキル** → 1件にまとめる。分けたままだと参照時にどちらを見ればよいか分からなくなる
- **既存の `examples/skills/` と実質同じ** → 取り込まず、既存を参照する
- 統合したら、そのことを報告に明記する（何件が何件になったか）

## 7. 書き出しと名前衝突の確認

`examples/skills/<slug>.md` に書く。slug は英語ケバブケース（既存ファイルと同じ流儀）。

書き終えたら**グローバルライブラリとの名前衝突を確認する**:

```powershell
$ex = Get-ChildItem "<REPO>\examples\skills\*.md" | Select-Object -ExpandProperty Name
$gl = Get-ChildItem "$env:USERPROFILE\.claude\pair-agent\skills\*.md" | Select-Object -ExpandProperty Name
$ex | Where-Object { $gl -contains $_ }
```

同名があるなら、それは「既にグローバルにあるスキル」。**内容が違うなら統合するか、slug を変えて別スキルにする。**

## 8. 配布

`skillimport.bat` で `examples/skills/*.md` をペア固有ライブラリへ配る:

```
skillimport.bat --list     # 何が入るかの下見（何も書かない）
skillimport.bat            # 未導入のものだけ取り込む（既存は保護）
skillimport.bat --force    # 既存も上書き
```

配布先は `~/.claude/pair-agent/skills/` と `~/.gemini/antigravity/pair-agent/skills/` の両方。

**既定では既存ファイルを上書きしない。** 同じディレクトリに師匠自身が育てたスキルが同居しているため。**実行前に必ず `--list` を見せて師匠の判断を仰ぐ。**

## 9. 報告

- 探索: N プロジェクト / M 件
- 取り込み: X 件（うち統合 Y 件）
- 除外: Z 件 —— **1件ずつ理由を添える**（「low: 特定製品の内部設計に密着」など）。黙って落とさない
- 名前衝突の有無
- 配布は実行したか（していないなら、実行するかを問う）

---

# library モード — スクリプトによるサーベイと pending レビュー

## 1. 起動時の判断

引数なし、または `--review` なし → サーベイを実行するか確認する:

> 「skill-survey スクリプトを実行してスキルを収集しますか？（既処理スキルはスキップされます）」

Yes → Phase 2 へ。No → Phase 3 へ。

## 2. サーベイ実行

```bash
python ~/.claude/pair-agent/tools/skill-survey.py
```

（スクリプトが見つからない場合は `python <PAIR_AGENT_REPO>/tools/skill-survey.py` を試す）

実行後、最新の `survey-report-<date>.md` を読んで結果を要約して師匠に伝える。

## 3. Pending スキルのレビュー

`~/.claude/pair-agent/skill-library/pending/` 内の `.md` ファイルを一覧表示する。

各スキルについて:
1. ファイルを読んで内容を師匠に提示（名前・スコア・汎化の要点・元プロジェクト）
2. 師匠に選択を求める:
   - **approve** → `approved/` に移動。`~/.claude/pair-agent/skills/` への昇格を提案（任意）
   - **reject** → `pending/` から削除。理由があれば記録
   - **edit** → 師匠の指示に従って内容を修正してから再提示
   - **skip** → 今回はスキップ（pending に残す）

複数ある場合は一件ずつ順番に処理する。

## 4. Approve 処理

`pending/<slug>.md` を `approved/<slug>.md` に移動する:
- フロントマターの `status: pending` → `status: approved` に変更
- `approved_date: <今日の日付>` を追加
- `~/.claude/pair-agent/skill-library/index.md` の該当行を更新（status を approved に）

昇格の提案:
> 「`~/.claude/pair-agent/skills/<slug>.md` としてグローバルスキルに昇格させますか？」

Yes → approved版をコピーし、survey metadata フィールド（source_project, source_path, survey_date, generalization_score, status）を削除した上で保存。

## 5. Reject 処理

- `pending/<slug>.md` を削除
- `.processed.json` には既にエントリがあるので再サーベイ対象にはならない
- 必要なら理由をメモとしてレポートに追記

## 6. 完了報告

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
harvest モードでは `project_roots` だけを使う（他のキーはスクリプト用）。

## モード選択の目安

- **すべてのプロジェクトスキルを一度に棚卸ししたい** → harvest（全体を見渡して統合できる）
- **前回サーベイ以降の差分だけ拾いたい** → library（`.processed.json` で追跡済み）
- **リポジトリ資産として配布したい** → harvest
- **師匠が1件ずつ approve/reject したい** → library
