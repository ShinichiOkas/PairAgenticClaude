---
name: テストヘルパ追加前に同名定義を Grep する
description: モジュールレベルのヘルパ関数を追加する前に、同名の既存定義が無いか必ず Grep する。Python は遅延束縛のため後定義が既存テストの呼び出しを乗っ取り一斉に壊す
type: feedback
maturity: confirmed
---

テストファイルにモジュールレベルのヘルパ関数（`_make_jwt`, `_make_request` のような名前）を追加する前に、同じファイル内（および同じテストディレクトリ内）に**同名の関数が既に定義されていないか**を Grep する。同名があれば既存を使うか、別名（`_make_jwt_with_exp` 等）にする。

**Why:** 実例——ファイル内に既存の `_make_jwt(payload: dict) -> str` があったにもかかわらず、末尾に別シグネチャの `_make_jwt(exp: int) -> str` を追記した。Python の遅延束縛により既存テストの呼び出しが新定義を解決してしまい、13件のテストが TypeError / AssertionError で一斉に失敗した。Grep していれば0秒で気づけた。

**How to apply:**
- ファイル末尾にヘルパを追記するときは、最低限そのファイル内を Grep する
- テストファイル全体を書き起こすときは特に注意する（衝突は後から AssertionError として発覚する）
- 命名ガイドライン: ヘルパは「何をするか＋何を返すか」を表す名前にする。`_make_jwt` のような汎用名は衝突しやすい
- 関連: [[per-call-mock-responses-for-retry-tests]]
