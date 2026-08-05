---
name: ユーザーが調整する挙動ルールは編集可能なポリシー文書に置く
description: 頻度・閾値・可否などユーザーが後から調整したい挙動ルールは、config へのハードコードでなく編集可能な Markdown ポリシー文書に置き、API で編集できるようにする
type: process
maturity: forming
---

ユーザー（師匠）が後から調整したい**挙動ルール**（頻度・閾値・可否・レート制御など）は、コードの config にハードコードするのでなく、**編集可能な Markdown ポリシー文書**に置く。データディレクトリ配下の `policies/*.md` に置き、`GET/PUT /policies/{name}` で編集できるようにする。

**Why:** 師匠の決定 —— 「レート規則は最初は設けない、スキルでコントロールできるのが望ましい。スキルにしておけば後から動的に変更できる」。

ハードコードすると変更に再デプロイまたはコード編集が要る。ポリシー文書なら師匠が**実行時に直接編集**でき、手続き記憶（Skill 育成）とも整合する。既存のポリシー読み取り機構と作法を揃えることで、ルールの置き場所が一箇所に集約され、将来の乖離を防げる。

**実装例:**

```yaml
enabled: true
urgency_floor: 0.7
min_defer_hours: 6
max_pushes_per_day: 2
quiet_start: 22
quiet_end: 8
```

- パーサが yaml ブロックを取り出してパースする。壊れていたら**安全側の既定**にフォールバックする
- 起動時に既定文書を生成する（`ensure_*`。**既存は上書きしない**）
- **マスターの ON/OFF だけは config 側**（安全弁）。細則は文書側、という役割分担

**How to apply:**

- 「これは師匠が後から変えたくなるか？」がルール文書行きの判断基準。頻度・閾値・可否・時間帯など
- パラメータは Markdown 内の yaml ブロックにして**決定的にパースする**。自由文の正規表現抽出より堅牢
- 破損・欠損時は安全側の既定にフォールバックする（`enabled: false` 等）
- 生成は `ensure_*`（既存を上書きしない）。編集経路は既存の policies API を再利用する
- **ただし「絶対に発火してはいけない安全弁（外向き機能のマスター）」は config 側に置く**
- 関連: [[outward-facing-features-ship-disabled-by-default]] / [[lifecycle-features-as-hook-plugins]] / [[externalize-only-what-varies-by-use]]
