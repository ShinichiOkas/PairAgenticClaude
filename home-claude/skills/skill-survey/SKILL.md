---
name: skill-survey
description: スキルライブラリのサーベイと自走レビュー。プロジェクト横断でスキルを収集・汎化し、pending スキルを並列のサブエージェントで判定・承認まで終えて事後報告する（師匠に 1 件ずつ聞かない）。リポジトリの examples/skills/ への取り込み（harvest）も担う。
user-invocable: true
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Skill Survey — スキルライブラリ管理

プロジェクト横断でスキルを収集し、汎化して再利用可能にする。**2つのモード**を持つ。

| モード | 出力先 | 汎化の実行者 | 使いどころ |
|---|---|---|---|
| **library**（既定） | `~/.claude/pair-agent/skill-library/pending/` | Haiku サブエージェント（1件ずつ判定。スクリプトは走査と取り込みだけで LLM を呼ばない） | 定期的な棚卸し。件数が多い・差分だけ拾いたい |
| **harvest** | Pair Agent リポジトリの `examples/skills/` | **私が全件を見渡して汎化**（件数が多ければ並列のサブエージェントに割って書かせ、重複統合と検査は私がする） | リポジトリ資産として配布したい。重複統合・取捨選択の判断が要る |

## 使い方

```
/skill-survey              # library モード: サーベイ実行 + pending レビュー
/skill-survey --review     # library モード: サーベイはスキップ、pending レビューのみ
/skill-survey --approve <slug>   # 特定スキルを直接 approve
/skill-survey --reject <slug>    # 特定スキルを直接 reject
/skill-survey --harvest    # harvest モード: 探索 → 汎化 → examples/skills/ へ取り込み
```

引数なしで起動されたら、**聞かずに推奨で着手する**: library（走査 → 並列の汎化 → ingest → 並列の自走レビュー → 事後報告）を既定とする。師匠が「配布したい」「既定にしたい」と言ったとき、または承認された中に配布物（`examples/skills/`）へ入れるべきものがあるときは、続けて harvest も回す。モードの目安は末尾「モード選択の目安」。
（2026-10-28 改め: 師匠の宣言 2026-10-27「徹底して自走。僕の判断など待たずに最速で、再並列で」→ [[skill-survey-review-runs-autonomously-in-parallel]]・[[speed-and-parallel-by-default]]。旧: まずどちらのモードかを師匠に確認する）

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

**この段階の事実は最後の報告に載せる**（ここで止めて待たない）:
- 何プロジェクトに何件あるか（`.gitkeep` のみのプロジェクトは除外して数える）
- 同名・同サイズのファイルが複数プロジェクトにあるか（＝既に横断展開されたスキル）
- 既に `examples/skills/` にある件数

## 2. 除外判定（読む前に落とすもの）

- `.gitkeep` / 空ファイル
- **`privateskills/` に同名ファイルがあるもの** — 師匠が意図的に非公開にしている。`examples/` は git 追跡されるので入れない
- `.agents/skills/` 配下でも、明らかに第三者由来（プロジェクトに同梱された外部スキル）のもの

## 3. 全件を自分で読む

`Read` で**全ファイルを読む**。並列に投げる。要約や grep で済ませない —— 汎化の判断は本文の細部（実際に踏んだ失敗・数値・コード例）に依存する。
件数が多いときは、共通の指示書 1 枚（下の 5 の方針・書き先・触ってはいけないもの）を書き、6〜7 件ずつサブエージェント（Sonnet）に割って**同時に**書かせる。担当の slug と絶対パスは起動プロンプトに具体値で書く（[[parallel-instruction-placeholders-get-taken-literally]]）。6 の重複統合と 7 の衝突確認・引用の照合は親がする。

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
- 固有の環境変数 → 「データルートの環境変数」のように概念の説明に置換（`{ENV_VAR_NAME}` のようなプレースホルダは、コードの中を除いて残さない）
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

**既定では既存ファイルを上書きしない。** 同じディレクトリに師匠自身が育てたスキルが同居しているため。`--list` で下見してから、そのまま既定（未導入のものだけ）で実行する（既存は保護されるので応答を待たない）。**`--force` は師匠が育てたスキルを上書きするので、師匠が明示したときだけ。**

## 9. 報告

- 探索: N プロジェクト / M 件
- 取り込み: X 件（うち統合 Y 件）
- 除外: Z 件 —— **1件ずつ理由を添える**（「low: 特定製品の内部設計に密着」など）。黙って落とさない
- 名前衝突の有無
- 配布の結果（`--list` の件数と、取り込んだ件数）

---

# library モード — サブエージェントによるサーベイと pending レビュー

**スクリプトは LLM を呼ばない**（師匠の宣言 2026-10-27「そもそも、サーベイのスクリプトはAPIコールを使う仕様なの？それ変更して」→ [[tool-scripts-do-not-call-the-api-directly]]）。
`skill-survey.py` は「走査して対象一覧を出す（discover）」と「結果をライブラリへ取り込む（ingest）」だけを持ち、
1件ずつの判定・汎化は Haiku のサブエージェントが担う。API キーは要らない。

## 1. 起動時の判断

引数なし → **聞かずに** Phase 2（サーベイ）へ進み、続けて Phase 3（自走レビュー）まで回す。既処理はパスと中身のハッシュで外れるので、対象は差分だけになる。
`--review` → Phase 3 へ直行する。
（2026-10-28 改め。旧: 「スキルを走査して汎化しますか？」と確認する）

## 2. サーベイ実行

スクリプトは `~/.claude/pair-agent/tools/skill-survey.py`（見つからない場合は `<PAIR_AGENT_REPO>/tools/skill-survey.py`）。

### 2-1. 走査（discover）

```bash
python ~/.claude/pair-agent/tools/skill-survey.py discover [--since <日時>] [--batch-size 8]
```

- `--since` — この日時（ISO 8601）以前に更新されたファイルは対象にせず、ingest で処理済みとして登録する。前回の取り込み（harvest のコミット時刻など）以降の差分だけを拾うときに使う
- 処理済みの判定は**パスと中身のハッシュ**で行う（`.processed.json` の `processed` ＋ `hashes`。ハッシュは改行を LF にそろえて取る）。取り込み後に中身が変わったファイルは対象に戻り、更新時刻だけが新しいファイル（git のチェックアウト等）は `--since` に拾われても再サーベイされない。`--since` は既処理でないファイルにだけ効く
- ハッシュの記録が無い旧来の登録は、ファイルの更新時刻が `.processed.json` の最終更新時刻（＝最後の ingest）以前なら既処理、それより新しければ対象に戻る。既処理にした分は、次の ingest でハッシュが記録される
- ⚠ 受け入れているリスク: 旧来の登録のうち、discover で読めなかったもの・走査範囲の外のものにはハッシュが付かない。走査範囲から外したプロジェクトを後で戻すと、その間の変更は拾えないことがある
- `.processed.json` が JSON として読めない（空ファイルを含む）・形が違う（`processed` が配列でない、`hashes` がオブジェクトでない）ときは、何も書かずにパスと理由を出して止まる（空として扱って全件を再サーベイしない）。discover・ingest とも同じ
- ポインタのスタブ（description が「ポインタ」で始まる。正典はグローバル側）は既定で対象から外し、処理済みとして登録する（`--since` の起点以前のものも、スタブとして数える）。対象に入れるときだけ `--include-stubs`
- ingest していない作業が残っていると止まる。捨ててよいと師匠が判断したときだけ `--force`
- ⚠ ingest が途中まで進んだ作業（ingest が出力先 —— pending・`.processed.json`・index・レポートのどれか —— に実際に書いた後で落ち、ingest 済みでない。manifest の `output_touched` が真。pending が 0 件でも、`.processed.json`・index・レポートを書いた後で落ちていれば該当する）は、`--force` でも作り直さず、「ingest をやり直す」案内（出力先に実際にある pending の件数を添える）を出して終了コード 1 で止まる（作り直すと控えが失われ、pending が重複する）。どうしても捨てるときだけ `discover --discard-partial`（書き済みの pending は残る。師匠が判断したときだけ）。**書き込みがエラーで失敗して、何も書けなかったもの**（pending の場所が通常ファイルで 1 件も書けない、など）は「書いた」に数えず、`output_touched` を偽に戻す。何も書く前に落ちたもの（書き込みの前の manifest の拒否・`--dry-run` を含む）と合わせて、これまでどおり `--force` で作り直せる。真のまま残るのは、控えの保存と書き込みの間でプロセスが強制終了された場合（安全な側）
- `--discard-partial` が外すのは「途中まで取り込んだ」状態の見張りだけ。途中まで取り込んでいない未 ingest の作業（discover の直後など）は、`--discard-partial` だけでは止まり（終了コード 1・何も消さない）、`--force` が要る。`--force` と併用すれば従来の `--force` と同じ
- manifest が壊れているときは、`--force`（または `--discard-partial` 単独）で作り直す。「壊れた」は、JSON として読めない・形が違う・控えの値が下の検査で拒否される、のすべて。このとき、途中まで取り込んだかを判定できなかった旨の警告を 1 行出す（取り込み済みの pending が出力先に残っていれば、重複しうる）。フラグ無しでは、何も消さずに止まる
- ingest は、書き込みの前に manifest の形を検める。控えは ingest 自身が書く形だけを通す: `pending_files`（idx → 出力先からの相対パス）の値は `pending/<名前>.md`（区切りは `/` か `\`・小文字の `.md`・名前は空でなく `:` `/` `\` と制御文字を含まない。2 つの idx が同じファイルを指すものは拒否）、`report_file`（ファイル名のみ）は `survey-report-<YYYY-MM-DD>.md` か `survey-report-<YYYY-MM-DD>-<2 以上の数>.md`（日付は `ingest_started_at` の日付と一致）、`ingest_started_at` は `YYYY-MM-DDTHH:MM:SS`（任意で小数秒と `Z` か `±HH:MM`。実在する日時）。`index.md`・`.processed.json`・`.survey-work/…` を指す値は拒否される。違えば何も書かずに終了コード 1
- manifest の検査の補足: `targets` の各要素の `idx`・`path`・`project`・`scope` は空でない文字列（無いのも拒否）。控えのキー（`ingest_started_at`・`report_file`・`pending_files`・`index_done`・`output_touched`・`hashes`）は、**無いのは受理し、あって型が違うもの（`null` を含む）は拒否する**（`null` を欠けている扱いにすると、index の節・レポートが二重になる）。`ingested_at` だけは、discover が `null` で書く
- 日付はこの機械のローカル日付。`ingest_started_at` はローカル時刻を UTC オフセット付きで書く（例 `2026-10-28T02:48:00+09:00`）。レポート名・index の節の日付・pending の `survey_date` は、その先頭 10 文字から作る（0 時をまたいだ再 ingest でも同じ）
- pending のファイル名は、汎化版の `name` から作る。`name` が無い、または `|` や記号だけでファイル名の本体が空になるときは、元ファイルの stem を使う（警告を出す）。stem からも空になるときは `skill-<idx>.md`
- meta 由来の文字列（エラー文言を含む）は、レポート・index・標準出力・標準エラーのどこでも 1 行にする: 改行と、ほかの制御文字（C0・DEL・C1〈U+0085 を含む〉・U+2028・U+2029）は空白 1 つに置き換える（repr の `
` 表記にはしない）。NBSP・ゼロ幅・双方向制御の文字はそのまま残す

書かれるもの（`<output_dir>/.survey-work/`）: `manifest.json`・`instructions.md`（判定・汎化の規約）・`batch-NN.json`・空の `out/`。

**件数は報告に載せ、確かめを待たずに起動する。** 標準出力の件数（見つかった数・既処理・中身が変わった・起点以前・スタブ・対象・バッチ数）は最後の報告に書く。
起動の前に、同じスキルの複製（別の作業ツリーやクローン）が深さ 2 で拾われていないかだけ自分で見る（`max_depth` で外せる）。
（2026-10-28 改め。旧: 件数を師匠に見せて、起動してよいかを確かめる）

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
- meta の `path` が manifest の `path` と違う結果（別のファイルの結果を書いた）もエラーになる（区切り文字と大文字小文字の違いは同じとみなす）
- ingest が途中で失敗したら、原因を直してもう一度 `ingest` を実行する（失敗時は Traceback ではなく、失敗した段階を出して終了コード 1）。どの段で落ちても、再 ingest で二重にならない:
  - pending: 書き先を manifest（`pending_files`）に控えてから書く。再 ingest では同じファイルに書き直す
  - レポート: 名前を manifest（`report_file`）に控えてから書く。再 ingest では同じ名前に書き直す（`-2` の別レポートを作らない）
  - index.md: 節の見出しに今回の ingest を識別する印（`<!-- skill-survey-run: … -->`）を入れる。印のある節は足し直さない（直して再 ingest した分の行だけが、その節の末尾に足される）
  - ingest の開始日時は最初の ingest で manifest（`ingest_started_at`）に控え、再 ingest でも同じ値を使う
- ingest は、何かを書く前に manifest の形（`targets`・`seed_processed`・`stubs`・`hashes`・控えの各キー）を検める。違えば何も書かずに理由を出して終了コード 1（控えのキーが無いのは受理。あるが型が違う・出力先の外を指すのは拒否）
- エラーの件を含んでいても、最後まで走った ingest は「ingest 済み」（終了コード 0）。エラーの件は処理済みにならず、次の discover で再び対象になる
- 処理済みに登録するときは、discover の時点の中身のハッシュを記録する（discover と ingest のあいだに変わったファイルは、次の discover で対象に戻る）
- 設定ファイルが JSON として読めない・型が違う（`project_roots` が文字列の配列でない等）ときは、何も書かずに理由を出して終わる
- 取り込み後、`survey-report-<date>.md`（同じ日の 2 回目以降は `survey-report-<date>-2.md`、`-3.md` …）を読んで結果を要約して師匠に伝える。skip（low）になった件は 1 件ずつ理由を添える

### 決定性の道具 `skill_library_ops.py`（師匠の宣言 2026-10-27「可能な限り作業は決定性のスクリプトにしろ」）

スクリプトは `<PAIR_AGENT_REPO>/tools/skill_library_ops.py`。既定は下見、書き込みは `--apply` のときだけ。LLM は呼ばない（`dedupe-candidates --judge-model` のときだけローカル Ollama）。

- 取り込み後・承認後の検査: `python tools/skill_library_ops.py verify [--approved-date YYYY-MM-DD]` — 引用行が元ファイルにあるか・`{NAME}` の残り（コード内は除外）・フロントマターを見る
- 並列レビューの割り当て: `python tools/skill_library_ops.py waves --size N --work-dir <dir> [--apply]` — 未割り当ての pending を `groupG<番号>.txt` に切る（番号で確定・既存は上書きしない）
- 承認後の目録更新: `python tools/skill_library_ops.py index [--apply]` — index.md の各行を approved / rejected の実際の置き場所に合わせる
- グローバルへの昇格: `python tools/skill_library_ops.py promote --list <名前の一覧> --approved-date YYYY-MM-DD [--apply]` — survey 用フィールドを外し provenance を足す（同名は上書きしない）
- 重複の洗い出し: `python tools/skill_library_ops.py dedupe-candidates [--out f.jsonl] [--judge-model qwen3.5:9b]` — 3-gram で候補を出し、指定時だけローカル Ollama で判定

## 3. Pending スキルのレビュー — 自走・並列（既定）

師匠の宣言（原文 2026-10-27）:

> 徹底して自走。僕の判断など待たずに最速で、再並列で

> 並列度が低いぞ！メモリもCPUもまだまだあるぞ！PCを遊ばせるな！

→ [[skill-survey-review-runs-autonomously-in-parallel]]（confirmed）。**師匠に 1 件ずつ approve / reject を聞かない。** 判定基準は親が決め、サブエージェントが並列に判定から実行まで終え、親が事後に判定一覧を報告する。

1. **割り当て**: pending を 8〜10 件ずつのグループに切り、グループファイル（1 行 1 絶対パス）に書く（`skill_library_ops.py waves` を使ってもよい）。プロジェクト由来の件（`source_path` がグローバル Skill の外）は 1 グループに寄せる（昇格の判断が要るため）
2. **共通の指示書を 1 枚書く**: 判定基準・実行手順・触ってはいけないもの・返す報告の形。グループファイルの絶対パスは**起動プロンプトに具体値で書く**（[[parallel-instruction-placeholders-get-taken-literally]]）
3. **グループごとに Sonnet（Tier 2）のサブエージェントを同時に起動する。** 各子は 1 件ごとに:
   - pending と元ファイル（`source_path`）を全文読み、⒜ 引用行（`> `）が元にそのまま在る ⒝ 個人情報（ユーザー名・ホームの絶対パス・実在の人名・私事）が無い ⒞ 規則・実測値・コード例・失敗の経緯が落ちていない ⒟ フロントマターが揃い `maturity` が元と同じ、を検める
   - **approve**（直す所なし）／**edit**（⒜〜⒟ を元から直して承認）／**reject**（特定製品の内部設計に密着して汎化で意味が失われる・空・壊れている）。グローバル Skill の写しであること自体は reject の理由にしない（approved はグローバルの汎化コピーを持つ場所）
   - approve / edit は下の 4 のとおり `approved/` に書いて pending を消す。別名で同じ `source_path` の旧版には `superseded_by: <新しいファイル名>` を足す（消さない）。reject は pending を消す
   - プロジェクト由来の件は、グローバルに同じ規則の Skill があるかを grep で探し「昇格候補: yes / no」を報告する
   - `index.md`・`.processed.json`・`.survey-work/`・グローバル Skill には触らない
4. **親は子を待たない。** 待つ間に別の独立作業（harvest・関連 Skill の手直し）を進め、子が 1 本終わるたびにその分を検める（全員を待って一括にしない）
5. **閉じるのは道具で**: `verify --approved-date <今日>`（引用・プレースホルダ・フロントマター）→ `index --apply` → 昇格候補 yes を `promote --apply`
6. 師匠に聞くのは、判定基準そのものが揺らぐときだけ。個々の判定では止まらない

師匠が「自分で 1 件ずつ見たい」と言ったときだけ、1 件ずつ提示する（既定ではしない）。
（2026-10-28 改め。旧: 1 件ずつ師匠に提示して approve / reject / edit / skip を選んでもらう）

## 4. Approve 処理

`pending/<slug>.md` を `approved/<slug>.md` に移動する:
- フロントマターの `status: pending` → `status: approved` に変更
- `approved_date: <今日の日付>` を追加
- `~/.claude/pair-agent/skill-library/index.md` の該当行を更新（status を approved に）

昇格は判定の一部として、聞かずに行う: プロジェクト由来でグローバルに同じ規則が無いものは `skill_library_ops.py promote --apply` でグローバルへ上げる（survey metadata フィールド〈source_project, source_path, survey_date, generalization_score, status〉を外し provenance を足す。同名は上書きしない）。上げたものは報告に列挙する（師匠は事後に取り消せる）。

## 5. Reject 処理

- `pending/<slug>.md` を削除
- `.processed.json` に既にエントリがあり、ソースの中身（ハッシュ）が変わらない限り再サーベイ対象にはならない（ソースが更新されたときは、reject したスキルも対象に戻る）
- 必要なら理由をメモとしてレポートに追記

## 6. 完了報告

事後に 1 回だけ報告する（応答を待たない）:

> 「レビュー完了: approve X件 / edit Y件 / reject Z件 / 昇格 W件」

edit と reject には理由を 1 件ずつ添える（黙って落とさない）。サーベイの件数（対象・中身が変わった・バッチ数）も同じ報告に載せる。

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
    ├── manifest.json         # 対象・起点以前・スタブ・discover 時点のハッシュ・ingest の控え（pending_files・report_file・ingest_started_at。ingest 済みなら ingested_at）
    ├── instructions.md       # サブエージェントに渡す判定・汎化の規約（固有名は概念の説明に置き換える。プレースホルダはコードの中を除いて残さない）
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
`project_roots` と `output_dir` は先頭の `~` がホームに展開される。`output_dir` は空でない文字列、`project_roots` の要素も空でない文字列でなければ設定エラー。展開した後で**絶対パスにならない**もの（`.`・`..`・`rel/dir`・`C:rel` など）は設定エラー（何も書かずに終了コード 1。カレントディレクトリで意味が変わるため）。
`also_survey_global: true` はグローバルスキル（数百件ある）も対象にする。差分の棚卸しでは `false` にしておくとよい。
harvest モードでは `project_roots` だけを使う（他のキーはスクリプト用）。

## モード選択の目安

- **すべてのプロジェクトスキルを一度に棚卸ししたい** → harvest（全体を見渡して統合できる）
- **前回サーベイ以降の差分だけ拾いたい** → library（`.processed.json` で追跡済み）
- **リポジトリ資産として配布したい** → harvest
- **速度・並列などの規則を他の環境でも既定にしたい** → library で承認したあと harvest（`examples/skills/` に入れて `skillimport.bat` で配る）
- **師匠が自分で 1 件ずつ見たいと言った** → library の pending を 1 件ずつ提示（既定ではしない）
