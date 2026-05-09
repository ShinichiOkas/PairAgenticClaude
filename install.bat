@echo off
setlocal enabledelayedexpansion

:: ESC character for colors
for /f "delims=" %%a in ('powershell -Command "[char]27"') do set "ESC=%%a"
set "RED=!ESC![0;31m"
set "GREEN=!ESC![0;32m"
set "YELLOW=!ESC![1;33m"
set "NC=!ESC![0m"

set "SCRIPT_DIR=%~dp0"
set "CLAUDE_HOME=%USERPROFILE%\.claude"
set "ANTIGRAVITY_HOME=%USERPROFILE%\.gemini\antigravity"
set "PAIR_AGENT_SRC=%SCRIPT_DIR%home-claude"
set "PROJECT_TEMPLATE=%SCRIPT_DIR%project-template"

if "%1"=="--project" goto project
if "%1"=="--uninstall" goto uninstall

:full
echo !GREEN![pair-agent]!NC! Installing Pair Agent to Claude and Antigravity ...

:: Ensure directories (Claude)
if not exist "%CLAUDE_HOME%\rules" mkdir "%CLAUDE_HOME%\rules"
if not exist "%CLAUDE_HOME%\skills" mkdir "%CLAUDE_HOME%\skills"
if not exist "%CLAUDE_HOME%\agents" mkdir "%CLAUDE_HOME%\agents"
if not exist "%CLAUDE_HOME%\pair-agent\skills" mkdir "%CLAUDE_HOME%\pair-agent\skills"
if not exist "%CLAUDE_HOME%\pair-agent\vision" mkdir "%CLAUDE_HOME%\pair-agent\vision"
if not exist "%CLAUDE_HOME%\pair-agent\corrections" mkdir "%CLAUDE_HOME%\pair-agent\corrections"

:: Ensure directories (Antigravity)
if not exist "%ANTIGRAVITY_HOME%\skills" mkdir "%ANTIGRAVITY_HOME%\skills"
if not exist "%ANTIGRAVITY_HOME%\pair-agent\skills" mkdir "%ANTIGRAVITY_HOME%\pair-agent\skills"
if not exist "%ANTIGRAVITY_HOME%\pair-agent\vision" mkdir "%ANTIGRAVITY_HOME%\pair-agent\vision"
if not exist "%ANTIGRAVITY_HOME%\pair-agent\corrections" mkdir "%ANTIGRAVITY_HOME%\pair-agent\corrections"

:: Copy project template
if exist "%PAIR_AGENT_SRC%\pair-agent\template" (
    :: Claude
    if exist "%CLAUDE_HOME%\pair-agent\template" rmdir /s /q "%CLAUDE_HOME%\pair-agent\template"
    xcopy /e /i /y "%PAIR_AGENT_SRC%\pair-agent\template" "%CLAUDE_HOME%\pair-agent\template" >nul
    :: Antigravity
    if exist "%ANTIGRAVITY_HOME%\pair-agent\template" rmdir /s /q "%ANTIGRAVITY_HOME%\pair-agent\template"
    xcopy /e /i /y "%PAIR_AGENT_SRC%\pair-agent\template" "%ANTIGRAVITY_HOME%\pair-agent\template" >nul
    echo !GREEN![pair-agent]!NC! Installed pair-agent/template (used by project-init skill^)
)

:: Handle CLAUDE.md / GEMINI.md
if exist "%CLAUDE_HOME%\CLAUDE.md" (
    findstr /c:"Pair Agent" "%CLAUDE_HOME%\CLAUDE.md" >nul
    if errorlevel 1 (
        copy /y "%CLAUDE_HOME%\CLAUDE.md" "%CLAUDE_HOME%\CLAUDE.md.pair-agent-backup" >nul
        echo !YELLOW![pair-agent]!NC! Backed up existing CLAUDE.md to CLAUDE.md.pair-agent-backup
        echo. >> "%CLAUDE_HOME%\CLAUDE.md"
        echo ^<!-- Pair Agent instructions appended below --^> >> "%CLAUDE_HOME%\CLAUDE.md"
        type "%PAIR_AGENT_SRC%\CLAUDE.md" >> "%CLAUDE_HOME%\CLAUDE.md"
        echo !GREEN![pair-agent]!NC! Appended Pair Agent instructions to existing CLAUDE.md
    ) else (
        copy /y "%PAIR_AGENT_SRC%\CLAUDE.md" "%CLAUDE_HOME%\CLAUDE.md" >nul
        echo !GREEN![pair-agent]!NC! Updated CLAUDE.md (Pair Agent content already present^)
    )
) else (
    copy /y "%PAIR_AGENT_SRC%\CLAUDE.md" "%CLAUDE_HOME%\CLAUDE.md" >nul
    echo !GREEN![pair-agent]!NC! Created CLAUDE.md
)
:: Copy to GEMINI.md
copy /y "%CLAUDE_HOME%\CLAUDE.md" "%ANTIGRAVITY_HOME%\GEMINI.md" >nul
echo !GREEN![pair-agent]!NC! Created/Updated GEMINI.md (copy of CLAUDE.md)

:: Rules
copy /y "%PAIR_AGENT_SRC%\rules\pair-agent-core.md" "%CLAUDE_HOME%\rules\" >nul

:: Skills (Deploy to both)
for /d %%d in ("%PAIR_AGENT_SRC%\skills\*") do (
    set "skill_name=%%~nxd"
    :: Claude
    if not exist "%CLAUDE_HOME%\skills\!skill_name!" mkdir "%CLAUDE_HOME%\skills\!skill_name!"
    copy /y "%%d\SKILL.md" "%CLAUDE_HOME%\skills\!skill_name!\" >nul
    :: Antigravity
    if not exist "%ANTIGRAVITY_HOME%\skills\!skill_name!" mkdir "%ANTIGRAVITY_HOME%\skills\!skill_name!"
    copy /y "%%d\SKILL.md" "%ANTIGRAVITY_HOME%\skills\!skill_name!\" >nul
    echo !GREEN![pair-agent]!NC! Installed skills/!skill_name!
)

:: Agents (Claude specific)
copy /y "%PAIR_AGENT_SRC%\agents\*.md" "%CLAUDE_HOME%\agents\" >nul
echo !GREEN![pair-agent]!NC! Installed agents (deliberation, retrospective, skill-executor^)

echo.
echo !GREEN![pair-agent]!NC! Installation complete!
goto end

:project
if exist ".pair-agent" (
    echo !YELLOW![pair-agent]!NC! .pair-agent/ already exists in current directory. Skipping.
) else (
    if exist "%CLAUDE_HOME%\pair-agent\template" (
        xcopy /e /i /y "%CLAUDE_HOME%\pair-agent\template" ".pair-agent" >nul
        echo !GREEN![pair-agent]!NC! Created .pair-agent/ in %CD% (from %%USERPROFILE%%\.claude\pair-agent\template\^)
    ) else if exist "%ANTIGRAVITY_HOME%\pair-agent\template" (
        xcopy /e /i /y "%ANTIGRAVITY_HOME%\pair-agent\template" ".pair-agent" >nul
        echo !GREEN![pair-agent]!NC! Created .pair-agent/ in %CD% (from %%USERPROFILE%%\.gemini\antigravity\pair-agent\template\^)
    ) else (
        xcopy /e /i /y "%PROJECT_TEMPLATE%\.pair-agent" ".pair-agent" >nul
        echo !YELLOW![pair-agent]!NC! Local template not found, used repository template instead.
    )

    :: Create GEMINI.md if CLAUDE.md exists
    if exist "CLAUDE.md" (
        if not exist "GEMINI.md" (
            copy /y "CLAUDE.md" "GEMINI.md" >nul
            echo !GREEN![pair-agent]!NC! Created GEMINI.md as a copy of CLAUDE.md
        )
    )

    :: Set created_at timestamp via PowerShell
    powershell -Command "$f='.pair-agent/current-sprint.json';$d=Get-Content $f|ConvertFrom-Json;$d.created_at=(Get-Date -Format 'o');$d|ConvertTo-Json|Set-Content $f" 2>nul
    echo !GREEN![pair-agent]!NC! Add to .gitignore if needed: .pair-agent/current-sprint.json
)
goto end

:uninstall
echo !YELLOW![pair-agent]!NC! Removing Pair Agent files from Claude and Antigravity ...
echo !YELLOW![pair-agent]!NC! (Learning data in pair-agent\ is preserved^)

:: Claude
del /q "%CLAUDE_HOME%\rules\pair-agent-core.md" 2>nul
del /q "%CLAUDE_HOME%\agents\*.md" 2>nul
:: Antigravity
del /q "%ANTIGRAVITY_HOME%\GEMINI.md" 2>nul

for %%s in (sprint-lifecycle agreement-document correction-record skill-learning retrospect vision-record project-start-empty project-start-existing vocabulary-capture project-init) do (
    rmdir /s /q "%CLAUDE_HOME%\skills\%%s" 2>nul
    rmdir /s /q "%ANTIGRAVITY_HOME%\skills\%%s" 2>nul
)

if exist "%CLAUDE_HOME%\CLAUDE.md.pair-agent-backup" (
    move /y "%CLAUDE_HOME%\CLAUDE.md.pair-agent-backup" "%CLAUDE_HOME%\CLAUDE.md" >nul
    echo !GREEN![pair-agent]!NC! Restored original CLAUDE.md from backup
)

echo !GREEN![pair-agent]!NC! Uninstall complete.
goto end

:end
echo.
echo Claude Home:      %CLAUDE_HOME%
echo Antigravity Home: %ANTIGRAVITY_HOME%
echo.
echo Learning data directory: %CLAUDE_HOME%\pair-agent\
echo   skills/      - Master's criteria (cross-project)
echo   vision/      - Vision records
echo   corrections/ - Correction records
echo.
echo To set up a project: cd your-project ^&^& "%SCRIPT_DIR%install.bat" --project
echo To start:            claude (or geminicli / antigravity)
endlocal
