---
name: 並行 push が拒否されたら重複ファイルの差分を先に確認してから rebase し両変更の共存を検証する
description: 同じ main へ複数エージェント/セッションが並行 push する環境で push が拒否されたら、いきなり rebase せず、リモートが触った重複ファイルの per-file 差分を先に確認して衝突範囲を把握し、rebase 後に自他の変更が共存していることを検証してから push する。
type: process
maturity: confirmed
---

複数のエージェント/セッションが同じ `main` へ push するペア環境で push が拒否されたら、
反射的に rebase する前に **リモートが何を触ったかを per-file の差分で先に確認**し、自分の変更と
重複するファイル（＝衝突しうる箇所）を特定する。rebase 後は自他の変更が **両方とも残って共存**
していることを検証してから push する。

**Why:** 実際に、ある作業の push が並行作業（別セッションの取り込み）に拒否された。`git diff <merge-base>..origin/main -- <file>` で**ファイル別に
確認**した結果、`--stat main..origin/main` の見かけ（あるファイル 54行・テスト -55行が変更）は
実は「**自分の未 push 変更が origin に無いだけ**」で、リモートが実際に触った重複は TODO 文書
1ファイルのみと判明。安心して rebase でき（自動3-wayマージで衝突ゼロ）、両作業が共存し
現在地行も保持されていることを確認してから push した。`--stat` の増減を早合点すると不要な手動衝突解決や事故を招く。

**How to apply:**

- push 拒否 → `git fetch` → `git log --oneline main..origin/main`（何が来たか）→
  **`git diff <merge-base>..origin/main -- <重複しそうなファイル>`**（リモートの実変更を per-file 確認）。
- `--stat main..origin/main` の増減数は「自分の未 push 差分」を含むので鵜呑みにしない。空 diff =
  そのファイルはリモート未変更（＝自分の変更のみ）。
- rebase 後は **自分の変更とリモートの変更が両方残っている**ことを grep/sed で機械検証してから push
  （見出し・追記行の共存確認）。ずれた行番号を含む自己参照は事故のもと。
- 破壊的操作（force push 等）はしない。自動3-wayマージ結果も必ず目視/機械検証する。
- 関連: [[speed-and-parallel-by-default]]
