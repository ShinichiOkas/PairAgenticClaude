---
name: 時刻の前後関係を検証するテストは時刻を明示注入する
description: 「A の後に B が起きた」を検証するテストで両方を now() 任せにしない。Windows のタイマ解像度は約15.6ms に量子化され、連続する2書き込みが同一値になって flaky 化する
type: process
maturity: confirmed
---

「A の後に B が起きた（`ts_A < ts_B`）」を検証するテストで、A と B の時刻を**両方 `datetime.now()` 任せにしてはいけない**。時刻は明示注入して順序を決定的にする。

**Windows の `datetime.now()` はシステムタイマ解像度（約 15.6ms）に量子化される。** 連続する2つの書き込みが同一 tick に落ちると、マイクロ秒表記の ISO8601 でも文字列が**完全一致**する。厳密比較（`<`）を使うプロダクトコードに対し、テストが実クロックの前進を前提にすると、確率的に `ts_A == ts_B` となって落ちる（＝ flaky）。

**Why:** 実例 —— 「固定済みマーク」を書いた直後に「更新」を書くと、同一 tick に落ちて2つのタイムスタンプが等しくなり、`consolidated_at < updated_at` の判定が偽になって対象が再浮上せず assert が落ちた。**実測 3回中1回赤。** 高速マシン・キャッシュ温間で顕在化した。

**マイクロ秒解像度に「上げる」だけでは、Windows の tick 量子化のため解決しない。**

**判定基準:**

1. 比較される時刻のうち**少なくとも一方を明示注入**し、順序を確定させる。`sleep` で実時間を進めるのは不可（遅い・依然として非決定的）
2. プロダクトの時刻書き込み API に**時刻注入口（`when=` / `updated_at=` 等の任意引数）**を用意する。既定 `None` は `now()` にフォールバックし、プロダクト既定挙動は変えない。**注入口はデータ移行（元時刻の保持）にも本番価値がある**
3. プロダクトの厳密比較（`<`）は基本正しい。「同時刻を境界に含める（`<=`）」への変更は別の副作用（同一 tick の生成・更新を常に境界内扱いして無限ループ化する等）を招く。**安易に緩めず、テスト側で決定化する**

**実装パターン:**

```python
# プロダクト側: 時刻注入口を対称に用意する
def update(self, item_id, *, summary=None, ..., updated_at: datetime | None = None):
    updated_iso = updated_at.isoformat() if updated_at is not None else now_iso
    ...

# テスト側: now() に頼らず順序を明示注入する
a = store.create(title="A")
t0 = a.updated_at
store.mark_consolidated(a.id, when=t0)                                   # 等しい → 未浮上
assert a.id not in ids(store.list_unconsolidated())
store.update(a.id, summary="x", updated_at=t0 + timedelta(seconds=1))    # 確実に後
assert a.id in ids(store.list_unconsolidated())                          # 再浮上
```

**関連:** [[windows-debug-output-cp932-safe]]（同じく Windows 固有のハマり） / [[schema-version-matches-migration-table]]（テスト環境固有の盲点という同種）
