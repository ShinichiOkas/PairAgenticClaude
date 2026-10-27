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
| **library**（既定） | `~/.claude/pair-agent/skill-library/pending/` | Haiku サブエージェント（1件ずつ判定。スクリプトは走査と取り込みだけで LLM を呼ばない） | 定期的な棚卸し。件数が多い・逐次レビューしたい |
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

# library モード — サブエージェントによるサーベイと pending レビュー

**スクリプトは LLM を呼ばない**（師匠の宣言 2026-10-27「そもそも、サーベイのスクリプトはAPIコールを使う仕様なの？それ変更して」→ [[tool-scripts-do-not-call-the-api-directly]]）。
`skill-survey.py` は「走査して対象一覧を出す（discover）」と「結果をライブラリへ取り込む（ingest）」だけを持ち、
1件ずつの判定・汎化は Haiku のサブエージェントが担う。API キーは要らない。

## 1. 起動時の判断

引数なし、または `--review` なし → サーベイを実行するか確認する:

> 「スキルを走査して汎化しますか？（既処理スキルはスキップされます）」

Yes → Phase 2 へ。No → Phase 3 へ。

## 2. サーベイ実行

スクリプトは `~/.claude/pair-agent/tools/skill-survey.py`（見つからない場合は `<PAIR_AGENT_REPO>/tools/skill-survey.py`）。

### 2-1. 走査（discover）

```bash
python ~/.claude/pair-agent/tools/skill-survey.py discover [--since <日時>] [--batch-size 8]
```

- `--since` — この日時（ISO 8601）以前に更新されたファイルは対象にせず、ingest で処理済みとして登録する。前回の取り込み（harvest のコミット時刻など）以降の差分だけを拾うときに使う
- 処理済みの判定は**パスと中身のハッシュ**で行う（`.processed.json` の `processed` ＋ `hashes`。ハッシュは改行を LF にそろえて取る）。取り込み後に中身が変わったファイルは対象に戻り、更新時刻だけが新しいファイル（git のチェックアウト等）は `--since` に拾われても再サーベイされない。`--since` は既処理でないファイルにだけ効く
- ハッシュの記録が無い旧来の登録は、ファイルの更新時刻が `.processed.json` の最終更新時刻（＝最後の ingest）以前なら既処理、それより新しければ対象に戻る。既処理にした分は、次の ingest でハッシュが記録される
- ポインタのスタブ（description が「ポインタ」で始まる。正典はグローバル側）は既定で対象から外し、処理済みとして登録する。対象に入れるときだけ `--include-stubs`
- ingest していない作業が残っていると止まる。捨ててよいと師匠が判断したときだけ `--force`

書かれるもの（`<output_dir>/.survey-work/`）: `manifest.json`・`instructions.md`（判定・汎化の規約）・`batch-NN.json`・空の `out/`。

**走らせる前に件数を師匠に見せる。** 標準出力の件数（見つかった数・既処理・起点以前・スタブ・対象・バッチ数）を伝え、サブエージェントを起動してよいかを確かめる。
同じスキルの複製（別の作業ツリーやクローン）が深さ 2 で拾われていないかもここで見る（`max_depth` で外せる）。

### 2-2. 判定・汎化（サブエージェント）

バッチ 1 つにつき 1 体、Haiku のサブエージェントを**並列で**起動する（`subagent_type: general-purpose`・`model: haiku`）。渡すのは 2 つのパスだけ:

- `.survey-work/instructions.md`（規約と、結果の書き方・出力先）
- 担当の `.survey-work/batch-NN.json`

各サブエージェントは `out/<idx>.meta.json`（全件）と `out/<idx>.md`（high / medium のみ）を書いて終わる。

### 2-3. 取り込み（ingest）

```bash
python ~/.claude/pair-agent/tools/skill-survey.py ingest --dry-run   # 件数と問題だけを見る
python ~/.claude/pair-agent/tools/skill-survey.py ingest
```

- `--dry-run` の「problems」を先に見る。特に **個人情報らしき文字列**（ユーザー名・ホームのパス）は、`out/<idx>.md` を直してから取り込む
- 次の件はエラーとして扱われ、pending に書かれず、処理済みにも登録されない（次の discover で再び対象になる）: 結果ファイルが欠けた／読めない、`generalizable_score` が `high`/`medium`/`low`/`skip`（小文字の完全一致）以外、high / medium なのに `.md` が空またはフロントマター（先頭の `---` で始まり `---` で閉じる区画）が無い。フロントマターに `name` が無いだけのものは警告で、pending には書かれる
- 処理済みに登録するときは、discover の時点の中身のハッシュを記録する（discover と ingest のあいだに変わったファイルは、次の discover で対象に戻る）
- 設定ファイルが JSON として読めない・型が違う（`project_roots` が文字列の配列でない等）ときは、何も書かずに理由を出して終わる
- 取り込み後、`survey-report-<date>.md`（同じ日の 2 回目以降は `survey-report-<date>-2.md`、`-3.md` …）を読んで結果を要約して師匠に伝える。skip（low）になった件は 1 件ずつ理由を添える

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
- `.processed.json` に既にエントリがあり、ソースの中身（ハッシュ）が変わらない限り再サーベイ対象にはならない（ソースが更新されたときは、reject したスキルも対象に戻る）
- 必要なら理由をメモとしてレポートに追記

## 6. 完了報告

> 「レビュー完了: approve X件 / reject Y件 / skip Z件」

---

## ライブラリ構造（参照用）

```
~/.claude/pair-agent/skill-library/
├── index.md                  # 全エントリカタログ
├── .processed.json           # 処理済みソースの追跡（processed: パスの配列 / hashes: パス → 中身のハッシュ）
├── pending/                  # 承認待ち
│   └── <slug>.md
├── approved/                 # 承認済み
│   └── <slug>.md
├── survey-report-<date>.md   # サーベイレポート
└── .survey-work/             # discover が作り ingest が読む作業ディレクトリ
    ├── manifest.json         # 対象・起点以前・スタブ・discover 時点のハッシュ（ingest 済みなら ingested_at）
    ├── instructions.md       # サブエージェントに渡す判定・汎化の規約
    ├── batch-NN.json         # サブエージェント 1 体ぶんの対象
    └── out/                  # <idx>.meta.json・<idx>.md（サブエージェントが書く）
```

## 設定ファイル

`~/.claude/pair-agent/skill-survey-config.json` でスキャン対象を管理:

```json
{
  "project_roots": ["~/work/develop"],
  "max_depth": 2,
  "output_dir": "~/.claude/pair-agent/skill-library",
  "also_survey_global": true
}
```

プロジェクトを追加したときはこのファイルに追記する。
`project_roots` と `output_dir` は先頭の `~` がホームに展開される。
`also_survey_global: true` はグローバルスキル（数百件ある）も対象にする。差分の棚卸しでは `false` にしておくとよい。
harvest モードでは `project_roots` だけを使う（他のキーはスクリプト用）。

## モード選択の目安

- **すべてのプロジェクトスキルを一度に棚卸ししたい** → harvest（全体を見渡して統合できる）
- **前回サーベイ以降の差分だけ拾いたい** → library（`.processed.json` で追跡済み）
- **リポジトリ資産として配布したい** → harvest
- **師匠が1件ずつ approve/reject したい** → library
