---
name: 消費専用リポジトリは push を機械的に封じる
description: 上流を fetch して使うだけのリポジトリでは push を一切行わない。git remote set-url --push origin no_push で誤 push を設定レベルでガードする
type: process
maturity: confirmed
---

別メンテナの上流リポジトリを clone/fork して**消費する側**として使っているリポジトリでは、リモートとの関係を **fetch only** とし、`git push` を一切実行しない。

意図の宣言だけに頼らず、設定レベルでガードを掛ける:

```
git remote set-url --push origin no_push
```

`git remote -v` で push 側が `no_push` になっていればガードが生きている。

**Why:** 師匠の明示宣言「このプロジェクトはリモートからはフェッチしかしない」（2026-05-28）。上流は別メンテナが管理しており、こちらは消費側。誤って push すれば上流を汚す外向きの不可逆操作になるため、「しないつもり」ではなく「できない設定」にしておく。

**How to apply:**
- 該当リポジトリでは `git push` / `git push --force` / `git push -u` を提案・実行しない。PR 作成（`gh pr create`）の提案もしない
- ローカル作業は `git fetch` / `git pull` / `git merge` / `git commit` まで
- 上流へ変更を提案する話が出たら、まず「push 禁止のはず」と確認する
- 万一 push が必要な場面が出たら、設定を変える前に必ず師匠に確認する
- 上流を消費するリポジトリを新しく持ち込んだ時点で、このガードの適用を検討する
- 関連: [[vendored-copy-diverges-both-ways]]（供給元がローカルにしか無い状況はこのガードの帰結として生まれる）
