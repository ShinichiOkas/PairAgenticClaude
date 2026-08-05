---
name: Python の行を無効化するときはコメント化でなく pass 置換
description: 取り込み時にコードを機械的に無効化する処理では、インデントされた行はコメント化するとブロックが空になり IndentationError になる。pass 置換でインデントと構文を保つ
type: reference
maturity: confirmed
---

コードを機械的に取り込んで一部の行を無効化する処理（ベンダリングの import 書き換え・シンボル呼び出しの no-op 化）では、**コメント化ではなく `pass` 置換**を使う。

```python
# 元コード
try:
    from somepkg.failures import STATS
    STATS.inc("auto_fix", fixes)
except ImportError:
    pass

# ❌ コメント化 → try ブロックが空になり IndentationError
try:
    # [sync: removed import] from somepkg.failures import STATS
    # [sync: STATS no-op] STATS.inc("auto_fix", fixes)
except ImportError:
    pass

# ✅ pass 置換 → インデントと構文を保持
try:
    pass  # [sync: removed import to non-vendored module] from somepkg.failures import STATS
    pass  # [sync: STATS no-op] STATS.inc("auto_fix", fixes)
except ImportError:
    pass
```

**Why:** 実際に踏んだ。取り込んだモジュールで `try:` ブロックの中身が全部コメントになり、`IndentationError: expected an indented block after 'try' statement` で import 自体が失敗した。`pass` を残せば「何もしないが構文的に有効」になり、`except ImportError: pass` も自然に素通りする。

**判定の簡略化:** **行頭にインデントがある無効化対象 → 必ず `pass` 置換**。インデント無し（モジュール scope の単独行）→ コメント化のみで OK。

適用が必要なブロック: `try` / `except` / `if` / `for` / `while` / `def` / `class` の中で、無効化対象がその行だけになりうる場合。

**How to apply:**

- 置換の実装では、正規表現でインデント（先頭の空白）をキャプチャして `${indent}pass ...` の形で再現する
- 形式は `pass  # [<マーカー>: <理由>] <元の行>` に統一する。`pass` で構文を満たし、マーカーで grep 可能にし、元コードを残して後追いできるようにする
- 「本物の実装に戻したい」「次の取り込み時にチェックしたい」ときに、マーカー1つの grep で全箇所が出る状態を保つ
- **過剰無効化に注意** — 関数内の `mkdir(...)` のように実行時に必要な副作用まで消すと、別の壊れ方をする。無効化対象の判定はインデント有無だけでなく、その行が実行時に必要かも見る
- 関連: [[transform-rules-grow-one-module-at-a-time]] / [[vendoring-keeps-proven-code-coexisting]]
