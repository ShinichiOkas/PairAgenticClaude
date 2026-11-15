@echo off
setlocal
REM Pair Agent Manager - environment setup (venv at manager\.venv).
REM This is separate from the repository root install.bat, which deploys
REM Pair Agent itself into %%USERPROFILE%%\.claude and .gemini.
REM Always operate on the directory this script lives in.
cd /d "%~dp0"
echo === Pair Agent Manager install ===

echo [1/5] Cleaning up stale install artifacts...
for %%F in (".venv\Scripts\*.deleteme") do (
    echo   Removing leftover renamed executable: %%~nxF
    del /q "%%F"
)
for /d %%D in (".venv\Lib\site-packages\~*") do (
    echo   Removing stale pip remnant: %%~nxD
    rd /s /q "%%D"
    if exist "%%D" echo   [WARN] Could not remove %%~nxD ^(a file in it is in use?^) -- ignoring it
)

if not exist ".venv\Scripts\python.exe" (
    echo [2/5] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 goto venv_failed
) else (
    echo [2/5] Using existing virtual environment
)

echo [3/5] Upgrading pip...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
if errorlevel 1 echo   [WARN] Failed to upgrade pip. Continuing with the current pip.

echo [4/5] Installing pamgr and dependencies (OmniAISDK is fetched from GitHub with git)...
".venv\Scripts\python.exe" -m pip install -e ".[dev]"
if errorlevel 1 goto pip_failed

echo [5/5] Self-check...
".venv\Scripts\python.exe" -m pamgr.selfcheck
if errorlevel 1 goto selfcheck_failed

echo.
echo Done. Start the GUI with:  run.bat
exit /b 0

:venv_failed
echo.
echo   [ERROR] Failed to create the virtual environment ^(python -m venv .venv^).
echo   [ERROR] Check that "python" on PATH is Python 3.11 or newer.
exit /b 1

:pip_failed
echo.
echo   [ERROR] pip install -e ".[dev]" failed -- see the error above.
echo   [ERROR] OmniAISDK is installed from https://github.com/ShinichiOkas/OmniAISDK with git.
echo   [ERROR] Make sure "git" is on PATH and github.com is reachable.
exit /b 1

:selfcheck_failed
echo.
echo   [ERROR] Self-check failed: the venv does not point at this checkout.
exit /b 1
