# Windows環境向けインストールスクリプトの実装計画

Windows 11環境でも本プロジェクトを簡単にインストール・利用できるように、`install.sh` と同等の機能を持つ `install.bat` を作成します。

## 変更内容の概要

1. **`install.bat` の新規作成**:
   - `install.sh` のロジックを Windows バッチファイル形式に移植。
   - `~/.claude` の代わりに `%USERPROFILE%\.claude` を使用。
   - ANSI エスケープシーケンスを用いた色付きログ出力をサポート。
   - `--project`, `--uninstall` フラグのサポート。

2. **`README.md` の更新**:
   - Windows 環境でのインストール手順（`install.bat` の実行）を追記。

## 導入計画

### [Windows Support]

#### [NEW] [install.bat](file:///s:/work/develop/PairAgenticClaude/install.bat)
- 環境変数設定 (`SCRIPT_DIR`, `CLAUDE_HOME` 等)。
- ログ出力関数 (ANSIカラー付き)。
- ディレクトリ作成ロジック。
- `CLAUDE.md` のバックアップと追記ロジック。
- `skills`, `agents`, `rules` のコピー。
- `--project` によるプロジェクト固有設定の配置。
- `--uninstall` による削除処理。

#### [MODIFY] [README.md](file:///s:/work/develop/PairAgenticClaude/README.md)
- 「インストール」セクションに Windows 版の手順を追加。
- 「プロジェクトへの導入」セクションに Windows 版のコマンド例を追加。

## 検証計画

### 手動検証
- Windows コマンドプロンプトで以下のコマンドを実行し、期待通りに動作することを確認する。
  - `install.bat` (フルインストール)
  - `install.bat --project` (カレントディレクトリへの配置)
  - `install.bat --uninstall` (アンインストール)
- `%USERPROFILE%\.claude` 内に正しくファイルが配置されているか確認。
- 色付きのログが正しく表示されるか確認。
