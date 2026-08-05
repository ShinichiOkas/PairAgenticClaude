---
name: GUI の見た目はヘッドレスブラウザ＋パッチ済みコピーで自分で撮って確認する
description: Webview 系 GUI の視覚検証は、assets をコピーして数点パッチを当て、ヘッドレス Chrome でスクショを撮ると自動化できる。canvas 描画は toDataURL で読み戻さないと真っ白に写る
type: reference
maturity: draft
---

デスクトップ Webview（pywebview 等）の GUI の見た目を、エージェントが自分で確認する手法。

## 手順

1. 一時データルートでサーバーを**別ポート**（例 8899）で起動する（→ [[e2e-temp-datadir-with-cache-junction]]）。見せたいデータはストア API で直接シードする
2. `assets/` を作業ディレクトリへコピーし、**コピーにのみ**パッチを当てる:
   - `let BASE_URL = null;` → `'http://127.0.0.1:8899'`（ホストからの ready イベントが来ないため）
   - `<body>` 直後に**ホスト API のスタブ**を挿入する。無いとイベントハンドラが `ReferenceError` で沈黙死し、描画されない:
     `window.pywebview = { api: new Proxy({}, { get: () => () => Promise.reject() }) }`
   - **SSE の購読開始を無効化する**（永遠に load 完了を妨げる）
   - `</body>` 直前に「ロード保留 img + 自動操作」を挿入する:
     `<img src="http://10.255.255.1/hold" style="display:none">`（非ルーティング先への接続保留で load イベントを遅らせる）+ サーバー待ちと自動クリックのポーリング
3. **ヘッドレス Chrome** で撮影する:
   ```
   chrome --headless --disable-gpu --user-data-dir=<一時プロファイル>
          --window-size=1620,1060 --timeout=8000
          --screenshot=<out.png> <file:///.../index.html>
   ```
4. 撮影後、**自分が起動したブラウザをコマンドラインで絞って kill** する

## 実際に踏んだ落とし穴

- **文字列 Replace の罠**: HTML の JS 文字列内に `</body>` / `<body>` が含まれることがある。ナイーブな全置換でタグ挿入すると、スクリプトが `</script>` で分断されてページが崩壊する。**タグへの挿入は必ず IndexOf / LastIndexOf の位置ベースで行う**
- `--virtual-time-budget` は `setInterval` が仮想時間を食い潰し、fetch 完了前に打ち切られる。**実時間 `--timeout` + ロード保留 img** の組み合わせが安定
- Edge の `--headless` は環境によって PNG を書かず動かない。Chrome を使う
- 別ポートなら稼働中の本番インスタンスと干渉しない

## canvas 描画は toDataURL で読み戻す

**ヘッドレス Chrome は `<canvas>` レイヤーをページに合成しない。** canvas に描くライブラリ（グラフ描画等）はそのまま撮ると**その部分だけ真っ白**に写る。ここで「描画されていない」と誤診しやすいが、描画自体は行われている。撮影直前に読み戻して `<img>` で貼り直す:

```js
window.network.redraw();                       // 最新状態を確実に描かせる
var c = document.querySelector("#graph-container canvas");
var img = new Image();
img.src = c.toDataURL("image/png");            // ここでピクセルが取れる
var r = c.getBoundingClientRect();
img.style.cssText = "position:fixed;left:"+r.left+"px;top:"+r.top+"px;width:"+r.width+
                    "px;height:"+r.height+"px;z-index:9999;";
document.body.appendChild(img);
```

- `--headless` / `--headless=new` のどちらでも同じ。新ヘッドレスにしても直らない
- **診断の順序**: まず `--dump-dom` で要素数・canvas サイズ・エラー配列を吐かせる。**状態は正しいのに絵だけ白い**なら合成の問題。ロジックを疑う前にこれを切り分ける
- 撮れた絵は **canvas の読み戻しであって実際の合成結果ではない**。色・重なり・レイヤー順の最終確認には使えないので、**報告時にその旨を必ず添える**（師匠の実機確認を省略しない）
- ホスト API を使わない構成のアプリなら、スタブ無しで実 assets をコピーし、「サンプル投入＋ボタン押下＋読み戻し」だけを `</body>` 直前に注入すれば、**HTML/JS/CSS を無改変のまま**検証できる
