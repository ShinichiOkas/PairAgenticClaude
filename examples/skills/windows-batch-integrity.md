---
name: Windowsバッチファイルの安全設計7鉄則
description: .bat は ASCII のみ・rem コメント・全上書き禁止・%~dp0+pushd/popd・setlocal・全パス引用・exit /b。cmd.exe の落とし穴を構造的に塞ぐ
type: domain
maturity: confirmed
---

Windows の `cmd.exe` 向けバッチファイル（`.bat` / `.cmd`）を書く・編集するときは、以下の鉄則をすべて守る。

## 鉄則1. エンコーディング — ASCII のみで書く

`.bat` はメッセージ・コメントを含め **ASCII 文字のみ**で書く（echo は英語にする）。

- **UTF-8 保存 + `chcp 65001` はほぼ100%破綻する。** `cmd.exe` はファイルを読み込んだ瞬間からシステム既定のコードページ（日本語環境では CP932）として解釈するため、`chcp 65001` に到達する前に BOM や非ASCII文字のバイト境界を誤認識し、コマンド記述自体が壊れる
- Shift-JIS（CP932）で保存すれば日本語も動くが、エディタ・Git の変換で崩れて再発した実績があり、**ASCII 限定が現行の確定ルール**（[[windows-batch-file-encoding]]）
- 呼び出す Python 側は先頭で `set PYTHONIOENCODING=utf-8` と `set PYTHONUTF8=1` を定義し、スクリプト内部の日本語処理は UTF-8 で安全に行う

## 鉄則2. コメントは `rem` のみ（`::` 全面禁止）

`::` はラベル `:` を重ねた非公式ハックで、`if` / `for` の括弧ブロック内で使うと `cmd.exe` がラベルと誤認して構文エラー（「システムは指定されたドライブを見つけることができません」等）で強制クラッシュする。

## 鉄則3. 既存ファイルの全上書き禁止

既存バッチを編集するとき、ファイル丸ごとの全置換をしない。ユーザーが手で足したパラメータ（デバイス設定・閾値等）や `rem` で残したバックアップ行が一瞬で消える。既存内容を読み、対象行のみピンポイントで書き換える。

## 鉄則4. ディレクトリ制御は `%~dp0` + `pushd`/`popd`

どこから起動されても動くよう、`pushd "%~dp0"` で自身の場所へ移動し、終了時に `popd` で復元する。`%~dp0` は末尾に `\` を含むため `"%~dp0scripts"` と書く（`\` を重ねない）。

## 鉄則5. 変数は `setlocal` / `endlocal` でローカル化

先頭（`@echo off` 直後）で `setlocal`、終了前に `endlocal`。呼び出し元シェルの環境を汚染しない。

## 鉄則6. パス・引数は必ずダブルクォーテーション

日本語・半角スペース入りパス（OneDrive 配下の「デスクトップ」等）で分割事故が起きる。引数は `"%~1"` の形で一度クォートを剥いでから囲み直す。

## 鉄則7. 終了は `exit /b %errorlevel%`

素の `exit` はユーザーが開いていたコマンドプロンプトのウィンドウごと閉じてしまう。`/b` でスクリプトプロセスのみ終了する。

## 標準テンプレート

```batch
@echo off
setlocal
rem ----------------------------------------------------------------------
rem  Windows Safe Batch Template (ASCII only)
rem ----------------------------------------------------------------------
pushd "%~dp0"
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo Starting...
".venv\Scripts\python.exe" "scripts\main.py"

if %errorlevel% neq 0 (
    echo [ERROR] Execution failed (Code: %errorlevel%)
    popd
    endlocal
    exit /b %errorlevel%
)

echo Done.
pause
popd
endlocal
exit /b 0
```

**Why:** 文字コード不整合・`::` によるブロック破綻・全上書きでのユーザー資産破壊・パス分割・プロンプト巻き添え終了という、計50回以上蓄積されたバッチの失敗パターンを根絶するために師匠が絶対ルールとして宣言（2026-05-30）。エンコーディングは当初「Shift-JIS 保存＋日本語」だったが、変換経路での再発を受けて 2026-07-03 に「ASCII のみ」へ更新された。

**How to apply:**
- `.bat` を新規作成・編集するたびにこの7点をチェックリストとして通す
- 保存後 `[^\x00-\x7F]` を Grep して非 ASCII が残っていないか検証する
- 自動化スクリプトの第一候補は PowerShell (.ps1)。`.bat` はユーザー向け起動口など必要な場面に限る
- 関連: [[windows-batch-file-encoding]] / [[windows-debug-output-cp932-safe]]
