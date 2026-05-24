---
name: 作業ディレクトリで Python を使うときは venv を積極的に使う
description: スクリプトで一次処理・調査作業を行う作業フォルダで Python を実行するときは venv を使い、本体環境を汚さない。
category: process
maturity: confirmed
domain_tags: [python, venv, scratch-dir, housekeeping]
proposed_by: ai
confirmed_by: human
created_at: 2026-05-24
updated_at: 2026-05-24
---

# ルール

スクリプトで一次処理・調査・スクレイピングなどを行う作業フォルダで Python を使うときは、必ず venv（`.venv` / `env` も可）を作って使う。本体の Python 環境にライブラリをインストールしない。

## Why

一次処理フォルダは様々なライブラリを試しに入れる場所になりやすく、放置すると本体環境が汚染される。venv で隔離することで副作用を閉じ込める。

## How to apply

- 作業フォルダで `pip install` を呼ぶ前に venv を起動する。
- venv が無ければ作る (`python -m venv venv`) → activate → install。
- ハウスキーピング（古いファイル整理）では venv を保護対象とし、削除・アーカイブしない。venv は再利用する。
- スクラッチの .py / .html / .md 等は古くなれば整理対象だが、venv は別扱い。

## 関連

- ハウスキーピング処理の保護パターンに `venv` / `.venv` / `env` / `pyvenv.cfg を含むディレクトリ` を含めること。
