---
name: スキーマバージョン定数とマイグレーション表の整合をテストで固定する
description: 新しい DDL を書いて MIGRATIONS に登録したら、同時に SCHEMA_VERSION も更新する。忘れるとマイグレーションがサイレントに走らず、tmp DB のテストでは検出できない
type: process
maturity: forming
---

新しい `_VXX_DDL` を書いて `MIGRATIONS[XX] = _VXX_DDL` に登録したら、**同時に `SCHEMA_VERSION = XX` も更新する**。

マイグレーション適用は `current_version >= SCHEMA_VERSION` で早期 return するのが一般的な実装で、**SCHEMA_VERSION が古いままだと新しい DDL を追加してもマイグレーションが走らない。しかもサイレントに無視される。**

**Why:** 実際に踏んだ。DDL を書き、`MIGRATIONS[10]` に登録し、`SCHEMA_VERSION = 9` を据え置いた。既存 DB は 9 のままで V10 が適用されず、更新 API が `OperationalError: no such column` で落ちた。API 側の try/except で握り潰されていたため、ユーザーには**「再起動するとリセットされる」**という全く別の症状として見えた。

**1179 テスト green でも検出されなかった** —— 一時ディレクトリのテストでは新規 DB が常に最新スキーマで作られるため、マイグレーション経路そのものが通らない。

**How to apply:**

DB スキーマを変更するコミットでは、以下を1セットで行う:

1. `_VXX_DDL = """ALTER TABLE ..."""` を追加
2. `MIGRATIONS[XX] = _VXX_DDL` に登録
3. **`SCHEMA_VERSION = XX` に更新** ← 忘れがち
4. **整合性テストで固定する:**

```python
def test_schema_version_matches_migrations_dict():
    assert max(MIGRATIONS.keys()) == SCHEMA_VERSION, (
        f"SCHEMA_VERSION ({SCHEMA_VERSION}) does not match "
        f"max(MIGRATIONS.keys()) ({max(MIGRATIONS.keys())})."
    )
```

- 「新規 DB を作ってテストする」だけでなく、**旧バージョンの DB を作ってマイグレーションを適用する**テストも1本持つ
- API レイヤーで `OperationalError` を握り潰さない。握り潰すと原因と症状が乖離して診断が遅れる
- 関連: [[test-inject-time-not-wall-clock]]（テスト環境固有の盲点という同種）
