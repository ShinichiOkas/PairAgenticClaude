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
set "PAIR_AGENT_SRC=%SCRIPT_DIR%home-claude"
set "PROJECT_TEMPLATE=%SCRIPT_DIR%project-template"

if "%1"=="--project" goto project
if "%1"=="--uninstall" goto uninstall

:full
echo !GREEN![pair-agent]!NC! Installing Pair Agent to %CLAUDE_HOME% ...

:: Ensure directories
if not exist "%CLAUDE_HOME%\rules" mkdir "%CLAUDE_HOME%\rules"
if not exist "%CLAUDE_HOME%\skills" mkdir "%CLAUDE_HOME%\skills"
if not exist "%CLAUDE_HOME%\agents" mkdir "%CLAUDE_HOME%\agents"
if not exist "%CLAUDE_HOME%\pair-agent\skills" mkdir "%CLAUDE_HOME%\pair-agent\skills"
if not exist "%CLAUDE_HOME%\pair-agent\vision" mkdir "%CLAUDE_HOME%\pair-agent\vision"
if not exist "%CLAUDE_HOME%\pair-agent\corrections" mkdir "%CLAUDE_HOME%\pair-agent\corrections"

:: Backup existing CLAUDE.md
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
        echo !GREEN![pair-agent]!NC! Updated CLAUDE.md (Pair Agent content already present)
    )
) else (
    copy /y "%PAIR_AGENT_SRC%\CLAUDE.md" "%CLAUDE_HOME%\CLAUDE.md" >nul
    echo !GREEN![pair-agent]!NC! Created CLAUDE.md
)

:: Rules
copy /y "%PAIR_AGENT_SRC%\rules\pair-agent-core.md" "%CLAUDE_HOME%\rules\" >nul
echo !GREEN![pair-agent]!NC! Installed rules/pair-agent-core.md

:: Skills
for /d %%d in ("%PAIR_AGENT_SRC%\skills\*") do (
    set "skill_name=%%~nxd"
    if not exist "%CLAUDE_HOME%\skills\!skill_name!" mkdir "%CLAUDE_HOME%\skills\!skill_name!"
    copy /y "%%d\SKILL.md" "%CLAUDE_HOME%\skills\!skill_name!\" >nul
    echo !GREEN![pair-agent]!NC! Installed skills/!skill_name!
)

:: Agents
copy /y "%PAIR_AGENT_SRC%\agents\*.md" "%CLAUDE_HOME%\agents\" >nul
echo !GREEN![pair-agent]!NC! Installed agents (deliberation, retrospective, skill-executor)

echo.
echo !GREEN![pair-agent]!NC! Installation complete!
goto end

:project
if exist ".pair-agent" (
    echo !YELLOW![pair-agent]!NC! .pair-agent/ already exists in current directory. Skipping.
) else (
    xcopy /e /i /y "%PROJECT_TEMPLATE%\.pair-agent" ".pair-agent" >nul
    echo !GREEN![pair-agent]!NC! Created .pair-agent/ in %CD%
    echo !GREEN![pair-agent]!NC! Add to .gitignore if needed: .pair-agent/current-sprint.json
)
goto end

:uninstall
echo !YELLOW![pair-agent]!NC! Removing Pair Agent files from %CLAUDE_HOME% ...
echo !YELLOW![pair-agent]!NC! (%CLAUDE_HOME%\pair-agent\ learning data is preserved)

del /q "%CLAUDE_HOME%\rules\pair-agent-core.md" 2>nul

for %%s in (sprint-lifecycle agreement-document correction-record skill-learning retrospect vision-record project-start-empty project-start-existing vocabulary-capture) do (
    rmdir /s /q "%CLAUDE_HOME%\skills\%%s" 2>nul
)

del /q "%CLAUDE_HOME%\agents\deliberation.md" 2>nul
del /q "%CLAUDE_HOME%\agents\retrospective.md" 2>nul
del /q "%CLAUDE_HOME%\agents\skill-executor.md" 2>nul

if exist "%CLAUDE_HOME%\CLAUDE.md.pair-agent-backup" (
    move /y "%CLAUDE_HOME%\CLAUDE.md.pair-agent-backup" "%CLAUDE_HOME%\CLAUDE.md" >nul
    echo !GREEN![pair-agent]!NC! Restored original CLAUDE.md from backup
)

echo !GREEN![pair-agent]!NC! Uninstall complete.
goto end

:end
echo.
echo Learning data directory: %CLAUDE_HOME%\pair-agent\
echo   skills/      - 師匠の判断基準（プロジェクトを跨ぐ）
echo   vision/      - ビジョン記録
echo   corrections/ - 叱責・修正記録
echo.
echo To set up a project: cd your-project ^&^& "%SCRIPT_DIR%install.bat" --project
echo To start: claude
endlocal
