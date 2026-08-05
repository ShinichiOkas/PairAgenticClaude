@echo off
setlocal enabledelayedexpansion

:: skillimport.bat - Import examples/skills/*.md into the pair-specific skill library
::
::   skillimport.bat            Import new skills only (existing files are kept)
::   skillimport.bat --force    Overwrite existing skills as well
::   skillimport.bat --list     Show what would be imported, change nothing
::
:: Claude and Antigravity are checked independently: a skill already present in
:: one library is still imported into the other.

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

set /a c_new=0, c_over=0, c_skip=0
set /a a_new=0, a_over=0, a_skip=0

echo !GREEN![skillimport]!NC! Source: %SRC%
if "%MODE%"=="list" echo !YELLOW![skillimport]!NC! --list: dry run, nothing will be written
echo.
echo   C=Claude  A=Antigravity   ^(+ import / ^= keep / ^! overwrite^)
echo.

for %%f in ("%SRC%\*.md") do (
    set "name=%%~nxf"

    :: --- Claude ---
    if exist "%CLAUDE_DST%\%%~nxf" (
        if "%MODE%"=="force" (
            if not "%MODE%"=="list" copy /y "%%f" "%CLAUDE_DST%\" >nul
            set /a c_over+=1
            set "tc=!YELLOW!C!!NC!"
        ) else (
            set /a c_skip+=1
            set "tc=C="
        )
    ) else (
        if not "%MODE%"=="list" copy /y "%%f" "%CLAUDE_DST%\" >nul
        set /a c_new+=1
        set "tc=!GREEN!C+!NC!"
    )

    :: --- Antigravity ---
    if exist "%ANTIGRAVITY_DST%\%%~nxf" (
        if "%MODE%"=="force" (
            if not "%MODE%"=="list" copy /y "%%f" "%ANTIGRAVITY_DST%\" >nul
            set /a a_over+=1
            set "ta=!YELLOW!A!!NC!"
        ) else (
            set /a a_skip+=1
            set "ta=A="
        )
    ) else (
        if not "%MODE%"=="list" copy /y "%%f" "%ANTIGRAVITY_DST%\" >nul
        set /a a_new+=1
        set "ta=!GREEN!A+!NC!"
    )

    echo   !tc! !ta!   !name!
)

echo.
if "%MODE%"=="list" (
    echo !GREEN![skillimport]!NC! Dry run -- nothing was written.
    echo   Claude:      would import !c_new! / overwrite !c_over! / keep !c_skip!
    echo   Antigravity: would import !a_new! / overwrite !a_over! / keep !a_skip!
    echo.
    echo   Run without --list to import, or --force to overwrite existing too.
) else (
    echo !GREEN![skillimport]!NC! Done.
    echo   Claude:      imported !c_new! / overwrote !c_over! / skipped !c_skip!
    echo   Antigravity: imported !a_new! / overwrote !a_over! / skipped !a_skip!
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
echo Imports examples\skills\*.md into BOTH of:
echo   %%USERPROFILE%%\.claude\pair-agent\skills\
echo   %%USERPROFILE%%\.gemini\antigravity\pair-agent\skills\
echo.
echo Each destination is checked independently, so a skill present in one
echo library is still imported into the other.

:end
endlocal
