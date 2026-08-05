@echo off
setlocal enabledelayedexpansion

:: skillimport.bat - Import examples/skills/*.md into the pair-specific skill library
::
::   skillimport.bat            Import new skills only (existing files are kept)
::   skillimport.bat --force    Overwrite existing skills as well
::   skillimport.bat --list     Show what would be imported, change nothing

:: ESC character for colors
for /f "delims=" %%a in ('powershell -Command "[char]27"') do set "ESC=%%a"
set "GREEN=!ESC![0;32m"
set "YELLOW=!ESC![1;33m"
set "NC=!ESC![0m"

set "SCRIPT_DIR=%~dp0"
set "SRC=%SCRIPT_DIR%examples\skills"
set "CLAUDE_DST=%USERPROFILE%\.claude\pair-agent\skills"
set "ANTIGRAVITY_DST=%USERPROFILE%\.gemini\antigravity\pair-agent\skills"

set "MODE=new"
if "%1"=="--force" set "MODE=force"
if "%1"=="--list" set "MODE=list"
if "%1"=="--help" goto usage
if "%1"=="-h" goto usage

if not exist "%SRC%" (
    echo !YELLOW![skillimport]!NC! Source not found: %SRC%
    goto end
)

if not "%MODE%"=="list" (
    if not exist "%CLAUDE_DST%" mkdir "%CLAUDE_DST%"
    if not exist "%ANTIGRAVITY_DST%" mkdir "%ANTIGRAVITY_DST%"
)

set /a n_new=0
set /a n_over=0
set /a n_skip=0

echo !GREEN![skillimport]!NC! Source: %SRC%
if "%MODE%"=="list" echo !YELLOW![skillimport]!NC! --list: dry run, nothing will be written
echo.

for %%f in ("%SRC%\*.md") do (
    set "name=%%~nxf"
    if exist "%CLAUDE_DST%\%%~nxf" (
        if "%MODE%"=="force" (
            copy /y "%%f" "%CLAUDE_DST%\" >nul
            copy /y "%%f" "%ANTIGRAVITY_DST%\" >nul
            set /a n_over+=1
            echo   !YELLOW!overwrite!NC!  !name!
        ) else (
            set /a n_skip+=1
            if "%MODE%"=="list" echo   skip       !name!  ^(already exists^)
        )
    ) else (
        if "%MODE%"=="list" (
            set /a n_new+=1
            echo   !GREEN!import!NC!     !name!
        ) else (
            copy /y "%%f" "%CLAUDE_DST%\" >nul
            copy /y "%%f" "%ANTIGRAVITY_DST%\" >nul
            set /a n_new+=1
            echo   !GREEN!import!NC!     !name!
        )
    )
)

echo.
if "%MODE%"=="list" (
    echo !GREEN![skillimport]!NC! Would import !n_new! / keep !n_skip! existing
    echo   Run without --list to import, or --force to overwrite existing too.
) else (
    echo !GREEN![skillimport]!NC! Imported !n_new! / overwrote !n_over! / skipped !n_skip!
)
echo.
echo   Claude:      %CLAUDE_DST%
echo   Antigravity: %ANTIGRAVITY_DST%
echo.
echo Existing skills are never overwritten unless --force is given,
echo because your own edits live in the same directory.
goto end

:usage
echo Usage: skillimport.bat [--list ^| --force]
echo.
echo   (no args)   Import skills that do not exist yet. Existing files are kept.
echo   --list      Show what would be imported. Changes nothing.
echo   --force     Also overwrite skills that already exist.
echo.
echo Imports examples\skills\*.md into:
echo   %%USERPROFILE%%\.claude\pair-agent\skills\
echo   %%USERPROFILE%%\.gemini\antigravity\pair-agent\skills\

:end
endlocal
