---
name: 「直したのに変わらない」ときは稼働プロセスの起動時刻を見る
description: 多重起動ガード付き常駐アプリはコード更新後に再 launch しても新コードがロードされない。コードや環境を疑う前に、動いているプロセスの起動時刻とコマンドラインを見る
type: process
maturity: confirmed
---

多重起動ガード＋トレイ常駐のアプリは、**コード修正後に再 launch しても修正が反映されない**。ガードが既存インスタンスを検出して前面化するだけで、**旧コードのプロセスが生き続ける**。「× で閉じる」もトレイ最小化であって終了ではない。

更新を反映する手順:

1. トレイメニュー「終了」で完全終了する（またはポートの listener PID を特定して停止する）
   ```powershell
   Get-NetTCPConnection -LocalPort 8778 -State Listen   # → Stop-Process
   ```
2. 再起動する

**プロセス世代の確認:**

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
  Where-Object { $_.CommandLine -match '<アプリ名>' } |
  Select-Object ProcessId, CreationDate, CommandLine | Format-List
```

**起動時刻がコード修正時刻より前なら、それは旧コードのプロセス。**

**Why:** 実機デバッグで、修正後の再起動操作がガードに吸収されて旧ビルドが動き続け、「修正したのに直らない」状態を踏んだ。ログの `already running on port XXXX — foregrounded existing window` がこのサイン。

**同じ穴を再度踏んだときの追加観察:**

- 走っていたプロセスは**午前起動のまま**で、午後の修正が未ロードだった。`CreationDate` で一発特定できた
- しかも**二重起動**していた（venv 版とシステム Python 版が両方）。**片方だけ止めても直らない**。システム Python 版は editable のソースが通っておらず、そもそも別環境で動く懸念もあった → 起動経路を1つに一本化し、**両方終了させてから**再起動する

**How to apply:**

- 修正を検証するときは、まずポート listener の PID / 起動時刻で「**どのビルドが動いているか**」を確認する
- 師匠に再起動を依頼するときは「**トレイの終了 → 再起動**」まで明示する。「再起動してください」だけでは伝わらない
- デバッグで「直したのに変わらない」と感じたら、**コードや環境より先に**旧プロセス残存を疑う
- 関連: [[verify-you-are-in-the-real-environment]]（どの環境か／どのプロセスか、という同型の取り違え） / [[kill-ai-started-processes]]
