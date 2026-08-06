---
name: ファイルDnDはサーバーアップロード経由でpathを返す
description: ブラウザ側でテキスト化せず、multipart でサーバーへ上げて保存先 path を設定に持たせる。実際の読み取り・変換は実行時にノード/処理側が行う
type: domain
maturity: confirmed
---

GUI へファイルを DnD で渡すときは、**ブラウザ側でテキスト化せず**、サーバーへ multipart アップロードして保存先の絶対 path を返してもらい、それを設定（`config.path` 等）にセットする。実際のファイル読み取り・変換（テキスト化、バイナリ→Markdown、CSV パース等）は**実行時に処理側のコードが行う**。

**Why:**

1. ブラウザはセキュリティ制約で絶対 path を取れない
2. ドロップ瞬間に `FileReader.readAsText` でテキスト化すると、バイナリ（pptx / pdf / xlsx）が文字化けゴミになる
3. 「処理は自分の責務を実行時に行う」原則と合致する

実際に最初は inline content 方式（ドロップ瞬間にテキスト化して設定へ埋め込み）を実装し、師匠の指摘で撤回した:

> 「ドロップした瞬間にconvertではなく、ワークフローをRUNしたときにロードしてコンバートするというのが期待する動作」

**How to apply:**
- サーバー: `POST /uploads` で multipart 受信、`.uploads/<uuid>_<original_name>` に binary-safe 保存、`{path, filename, size}` を返す
- フロント: ドロップ → `FormData` で POST → 返り値の path を設定にセット
- `.uploads/` は `.gitignore` に入れる
- テキスト化のキャッシュが欲しくなっても、まずは実行時ロードで進める（キャッシュは将来別レイヤで対応可能）
- 関連: [[user-builds-workflows-ai-fixes]] / [[llm-not-for-format-discipline]]
