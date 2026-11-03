# 判定役の指示（スキル仕分け・班ごと）

あなたは判定役です。対話せず、質問せず、担当の 1 班（54 件）を判定して TSV 1 ファイルに書き出し、短く報告して終わってください。

## 目的
ペア固有スキル（`~/.claude/pair-agent/skills/`）の棚卸し。各スキルを active / project / archive のいずれかに仕分けます。根拠は 1 行で残します（師匠が後で見直すため）。

## 読むもの（この順で）
1. 判定基準: `C:\Users\0000950207\.claude\pair-agent\GOVERNANCE.md` の §1（active・project・archive の定義）。他の節は読まなくてよい。
2. 班一覧: 担当の `batch-NN.txt`（1 行 1 件・拡張子なしのスキル名・54 件）。
3. 各スキル本文: `C:\Users\0000950207\.claude\pair-agent\skills\<スキル名>.md` を全文。1 件ずつ Read（並列でよい）。
4. 書式の見本（参照のみ。内容は写さない）: `batch-01.tsv`

作業フォルダ（以下 `cls\` と書く）: `C:\Users\0000950207\AppData\Local\Temp\claude\778e87595a7d3e63\0e4ebe9b-f99a-4cc5-bcdc-a7888f59db43\scratchpad\cls\`

## 書くもの
`cls\batch-NN.tsv`（UTF-8・改行は LF・BOM なし。NN は担当の班番号）

- 1 行目はヘッダ。列の名前はこの順、この綴りで、区切りは半角のタブ文字（Tab）:
  skill, class, target, core, proper_nouns, reason, confidence
- 2 行目以降は班一覧と同じ順で 54 行（1 件 1 行）。
- フィールドの中にタブと改行を入れない。
- skill: 班一覧のスキル名をそのまま。
- class: active / project / archive のいずれか。
- target: class が project のときだけ、`C:\Users\0000950207\work\` の直下にある既存ディレクトリ名（大文字小文字もそのまま）。それ以外は空。
- core: 原則を一行で（日本語・40 字以内）。
- proper_nouns: 本文中の固有名（プロジェクト名・ツール名・ファイル名・フェーズ名など）をカンマ区切りで。無ければ空。
- reason: その class にした根拠を一行で（日本語・80 字以内・事実だけ）。
- confidence: high / mid / low のいずれか。

## 判定規則（全班で同じに当てる）
1. `a2a-` で始まるスキル（6 件）は active。confidence は high。reason は「GOVERNANCE §1 の既知の例外」。
2. active は次の (a) と (b) を両方満たすものだけ。
   (a) 固有名を全部消しても原則が成立する。
   (b) 別のプロジェクト、または別のスプリント・フェーズで再現したことが、本文から確認できる（2 文脈以上）。
   例外: 本文に、師匠（ユーザー）が全プロジェクトに効く規範として宣言した文言があるものは、事例が 1 件でも active にしてよい。confidence は mid。
3. project: 原則が特定プロジェクトの機構・構造・固有名に密着していて、固有名を消すと成立しないもの。target はそのプロジェクトのディレクトリ名で、`C:\Users\0000950207\work\` に実在すること。
   - 実在しない対象しか出てこないときは archive にし、reason に「対象リポジトリ不在」と書く。
4. archive: active にも project にも当たらないもの。事例が本文に 1 件だけで宣言の例外にも当たらないもの、技術的な観測や一時的な手順、判断材料が足りないもの。迷ったら archive。
5. confidence: high = 規則に明確に当たる。mid = 規則に当てたが判断の余地がある。low = どちらにも倒れうる。
6. 本文が読めない・空のときは class=archive、reason=「読込不能」、confidence=low。

## 禁止
- ファイルの移動・削除・編集、git の操作。書いてよいのは担当の TSV 1 ファイルだけ。
- `C:\Users\0000950207\.claude\pair-agent\` の下への書き込み。
- 質問。判断に迷ったら規則に従い、confidence を下げて書く。

## 完了の確認と報告
1. 書いたら PowerShell で次を確かめる: 行数（ヘッダ＋54）、全行が 7 列、班一覧と一致（重複・欠落なし）、class と confidence の値が規定どおり。直すべきところは直す。
2. 最後の返答は 10 行以内。次だけを書く: 出力パス、行数、class の件数、confidence の件数、迷った例 3 件（スキル名と理由を 1 行ずつ）。本文の引用や長い説明は書かない。
