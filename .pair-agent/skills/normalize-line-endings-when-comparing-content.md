---
name: 内容の比較は改行と空白を除いて行う — バイト比較は書く直前の「計画後に変わったか」の確認だけに使う
description: 内容が同じかの判定は改行・空白を正規化して比べる。新しい clone（autocrlf で CRLF）は作業ツリー（LF）とバイトで 42 件中 16 件違い、同じ 35 ファイルを配り直す計画になった。バイトのハッシュは書く直前の確認だけに使う
type: technique
maturity: draft
created_at: 2026-11-15
source: Pair Agent Manager（manager/pamgr/changes.py の ckey）。2026-11-15 の実データでの確認
proposed_by: ai
approved_by: none（AI の観測。未承認）
domain_tags: [manager, normalization, crlf, line-endings, git]
---

## 内容

内容が同じか違うかの判定は、改行コードと空白の差を取り除いて比べる（`changes.ckey`）。

- バイトのハッシュを使うのは、**書く直前に「計画してから対象が変わったか」を見る確認**だけ
- 違いが改行・空白だけなら、配り直さない

## Why

実測（2026-11-15）。新しい clone は autocrlf で CRLF になる。作業ツリー（LF）と比べると、42 ファイル中 16 ファイルがバイトで違った。この判定のまま点検（sweep）を回すと、中身が同じ 35 ファイルを配り直す計画になった。

差分が改行だけの配布は、対象の `git diff` を全行変更に見せ、他 PC との同期で衝突を作る。

## How to apply

- 比較の関数は 1 つに決め（`changes.ckey`）、計画・履歴の当たり判定・取り消しの印がすべて通す
- 書く直前の確認は、正規化前のバイトで行う（正規化の差で上書きを見逃さないため）
- 書くときの改行は、対象の既存ファイルの改行に合わせる（結合のときに CRLF と LF を混ぜない）
