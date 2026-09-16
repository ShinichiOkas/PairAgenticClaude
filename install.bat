@echo off
setlocal EnableDelayedExpansion

for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "GREEN=!ESC![0;32m"
set "YELLOW=!ESC![1;33m"
set "NC=!ESC![0m"

set "SCRIPT_DIR=%~dp0"
set "CLAUDE_HOME=%USERPROFILE%\.claude"
set "ANTIGRAVITY_CONFIG=%USERPROFILE%\.gemini\config"
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
if not exist "%CLAUDE_HOME%\pair-agent\skill-library\pending" mkdir "%CLAUDE_HOME%\pair-agent\skill-library\pending"
if not exist "%CLAUDE_HOME%\pair-agent\skill-library\approved" mkdir "%CLAUDE_HOME%\pair-agent\skill-library\approved"
if not exist "%CLAUDE_HOME%\pair-agent\tools" mkdir "%CLAUDE_HOME%\pair-agent\tools"

:: Ensure directories (Antigravity)
if not exist "%ANTIGRAVITY_CONFIG%\rules" mkdir "%ANTIGRAVITY_CONFIG%\rules"
if not exist "%ANTIGRAVITY_CONFIG%\skills" mkdir "%ANTIGRAVITY_CONFIG%\skills"
if not exist "%ANTIGRAVITY_CONFIG%\agents" mkdir "%ANTIGRAVITY_CONFIG%\agents"
if not exist "%ANTIGRAVITY_CONFIG%\pair-agent\skills" mkdir "%ANTIGRAVITY_CONFIG%\pair-agent\skills"
if not exist "%ANTIGRAVITY_CONFIG%\pair-agent\vision" mkdir "%ANTIGRAVITY_CONFIG%\pair-agent\vision"
if not exist "%ANTIGRAVITY_CONFIG%\pair-agent\corrections" mkdir "%ANTIGRAVITY_CONFIG%\pair-agent\corrections"
if not exist "%ANTIGRAVITY_CONFIG%\pair-agent\tools" mkdir "%ANTIGRAVITY_CONFIG%\pair-agent\tools"

:: Copy skill-survey config (only if not already customized)
if not exist "%CLAUDE_HOME%\pair-agent\skill-survey-config.json" (
    copy /y "%PAIR_AGENT_SRC%\pair-agent\skill-survey-config.json" "%CLAUDE_HOME%\pair-agent\" >nul
    echo !GREEN![pair-agent]!NC! Installed pair-agent/skill-survey-config.json
)

:: Copy tools
for %%t in (skill-survey.py survey-dev-prefs.py derive_roles.py simulate_mk.py check_skills.py check_report.py emit_claude.py emit_agents.py run_workflow.py deny_read.py measure_agent_usage.py) do (
    if exist "%SCRIPT_DIR%tools\%%t" (
        copy /y "%SCRIPT_DIR%tools\%%t" "%CLAUDE_HOME%\pair-agent\tools\" >nul
        copy /y "%SCRIPT_DIR%tools\%%t" "%ANTIGRAVITY_CONFIG%\pair-agent\tools\" >nul
    )
)
echo !GREEN![pair-agent]!NC! Installed tools into ~/.claude/ and ~/.gemini/config/

:: Copy project template
if exist "%PAIR_AGENT_SRC%\pair-agent\template" (
    :: Claude
    if exist "%CLAUDE_HOME%\pair-agent\template" rmdir /s /q "%CLAUDE_HOME%\pair-agent\template"
    xcopy /e /i /y "%PAIR_AGENT_SRC%\pair-agent\template" "%CLAUDE_HOME%\pair-agent\template" >nul
    :: Antigravity
    if exist "%ANTIGRAVITY_CONFIG%\pair-agent\template" rmdir /s /q "%ANTIGRAVITY_CONFIG%\pair-agent\template"
    xcopy /e /i /y "%PAIR_AGENT_SRC%\pair-agent\template" "%ANTIGRAVITY_CONFIG%\pair-agent\template" >nul
    echo !GREEN![pair-agent]!NC! Installed pair-agent/template
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
        echo !GREEN![pair-agent]!NC! Updated CLAUDE.md
    )
) else (
    copy /y "%PAIR_AGENT_SRC%\CLAUDE.md" "%CLAUDE_HOME%\CLAUDE.md" >nul
    echo !GREEN![pair-agent]!NC! Created CLAUDE.md
)
:: Copy to GEMINI.md
copy /y "%PAIR_AGENT_SRC%\GEMINI.md" "%ANTIGRAVITY_CONFIG%\GEMINI.md" >nul
echo !GREEN![pair-agent]!NC! Created/Updated GEMINI.md in ~/.gemini/config/

:: Rules (Deploy to both)
copy /y "%PAIR_AGENT_SRC%\rules\pair-agent-core.md" "%CLAUDE_HOME%\rules\" >nul
copy /y "%PAIR_AGENT_SRC%\rules\pair-agent-core.md" "%ANTIGRAVITY_CONFIG%\rules\" >nul
echo !GREEN![pair-agent]!NC! Installed rules/pair-agent-core.md

:: Skills (Deploy to both)
for /d %%d in ("%PAIR_AGENT_SRC%\skills\*") do (
    set "skill_name=%%~nxd"
    :: Claude
    if not exist "%CLAUDE_HOME%\skills\!skill_name!" mkdir "%CLAUDE_HOME%\skills\!skill_name!"
    copy /y "%%d\SKILL.md" "%CLAUDE_HOME%\skills\!skill_name!\" >nul
    :: Antigravity
    if not exist "%ANTIGRAVITY_CONFIG%\skills\!skill_name!" mkdir "%ANTIGRAVITY_CONFIG%\skills\!skill_name!"
    copy /y "%%d\SKILL.md" "%ANTIGRAVITY_CONFIG%\skills\!skill_name!\" >nul
    echo !GREEN![pair-agent]!NC! Installed skills/!skill_name!
)

:: Agents (Deploy to both)
copy /y "%PAIR_AGENT_SRC%\agents\*.md" "%CLAUDE_HOME%\agents\" >nul
copy /y "%PAIR_AGENT_SRC%\agents\*.md" "%ANTIGRAVITY_CONFIG%\agents\" >nul
echo !GREEN![pair-agent]!NC! Installed agents (deliberation, retrospective, skill-executor)

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
    ) else if exist "%ANTIGRAVITY_CONFIG%\pair-agent\template" (
        xcopy /e /i /y "%ANTIGRAVITY_CONFIG%\pair-agent\template" ".pair-agent" >nul
        echo !GREEN![pair-agent]!NC! Created .pair-agent/ in %CD% (from %%USERPROFILE%%\.gemini\config\pair-agent\template\^)
    ) else (
        xcopy /e /i /y "%PROJECT_TEMPLATE%\.pair-agent" ".pair-agent" >nul
        echo !YELLOW![pair-agent]!NC! Local template not found, used repository template instead.
    )

    if not exist ".agents\skills" mkdir ".agents\skills"
    if not exist ".agents\agents" mkdir ".agents\agents"
    if not exist ".agents\workflows" mkdir ".agents\workflows"

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
del /q "%ANTIGRAVITY_CONFIG%\GEMINI.md" 2>nul
del /q "%ANTIGRAVITY_CONFIG%\rules\pair-agent-core.md" 2>nul
del /q "%ANTIGRAVITY_CONFIG%\agents\*.md" 2>nul

for %%s in (sprint-lifecycle agreement-document correction-record skill-learning retrospect vision-record project-start-empty project-start-existing vocabulary-capture project-init skill-survey) do (
    rmdir /s /q "%CLAUDE_HOME%\skills\%%s" 2>nul
    rmdir /s /q "%ANTIGRAVITY_CONFIG%\skills\%%s" 2>nul
)
del /q "%CLAUDE_HOME%\pair-agent\tools\skill-survey.py" 2>nul

if exist "%CLAUDE_HOME%\CLAUDE.md.pair-agent-backup" (
    move /y "%CLAUDE_HOME%\CLAUDE.md.pair-agent-backup" "%CLAUDE_HOME%\CLAUDE.md" >nul
    echo !GREEN![pair-agent]!NC! Restored original CLAUDE.md from backup
)

echo !GREEN![pair-agent]!NC! Uninstall complete.
goto end

:end
echo.
echo Claude Home:        %CLAUDE_HOME%
echo Antigravity Config: %ANTIGRAVITY_CONFIG%
echo.
echo Learning data directory: %CLAUDE_HOME%\pair-agent\
echo   skills/      - Master's criteria (cross-project)
echo   vision/      - Vision records
echo   corrections/ - Correction records
echo.
echo To set up a project: cd your-project ^&^& "%SCRIPT_DIR%install.bat" --project
echo To start:            claude (or geminicli / antigravity)
endlocal
