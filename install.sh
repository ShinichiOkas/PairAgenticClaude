#!/usr/bin/env bash  
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  
CLAUDE_HOME="${HOME}/.claude"  
ANTIGRAVITY_CONFIG="${HOME}/.gemini/config"
PAIR_AGENT_SRC="${SCRIPT_DIR}/home-claude"  
PROJECT_TEMPLATE="${SCRIPT_DIR}/project-template"

RED='\033[0;31m'  
GREEN='\033[0;32m'  
YELLOW='\033[1;33m'  
NC='\033[0m'

info()  { echo -e "${GREEN}[pair-agent]${NC} $1"; }  
warn()  { echo -e "${YELLOW}[pair-agent]${NC} $1"; }  
error() { echo -e "${RED}[pair-agent]${NC} $1"; }

# --- Project-only install ---  
if [[ "${1:-}" == "--project" ]]; then  
    if [[ -d ".pair-agent" ]]; then  
        warn ".pair-agent/ already exists in current directory. Skipping."  
    else  
        if [[ -d "${CLAUDE_HOME}/pair-agent/template" ]]; then  
            cp -r "${CLAUDE_HOME}/pair-agent/template" .pair-agent  
            info "Created .pair-agent/ in $(pwd) (from ~/.claude/pair-agent/template/)"  
        elif [[ -d "${ANTIGRAVITY_CONFIG}/pair-agent/template" ]]; then
            cp -r "${ANTIGRAVITY_CONFIG}/pair-agent/template" .pair-agent
            info "Created .pair-agent/ in $(pwd) (from ~/.gemini/config/pair-agent/template/)"
        else  
            cp -r "${PROJECT_TEMPLATE}/.pair-agent" .  
            warn "Local template not found, used repository template instead."  
        fi  

        # Create .agents/ structure for Antigravity
        mkdir -p .agents/skills .agents/agents .agents/workflows

        # Create GEMINI.md if CLAUDE.md exists
        if [[ -f "CLAUDE.md" && ! -f "GEMINI.md" ]]; then
            cp "CLAUDE.md" "GEMINI.md"
            info "Created GEMINI.md as a copy of CLAUDE.md"
        fi

        # Set created_at timestamp  
        if command -v python3 &>/dev/null; then  
            python3 -c "  
import json, datetime  
with open('.pair-agent/current-sprint.json', 'r+') as f:  
    d = json.load(f)  
    d['created_at'] = datetime.datetime.now(datetime.timezone.utc).isoformat()  
    f.seek(0); json.dump(d, f, indent=2); f.truncate()  
" 2>/dev/null || true  
        fi  
        info "Add to .gitignore if needed: .pair-agent/current-sprint.json"  
    fi  
    exit 0  
fi

# --- Uninstall ---  
if [[ "${1:-}" == "--uninstall" ]]; then  
    warn "Removing Pair Agent files from ~/.claude/ and ~/.gemini/config/ ..."  
    warn "(Learning data in pair-agent/ is preserved)"

    # Claude Code
    rm -f  "${CLAUDE_HOME}/CLAUDE.md.pair-agent-backup" 2>/dev/null || true  
    rm -f  "${CLAUDE_HOME}/rules/pair-agent-core.md" 2>/dev/null || true  
    rm -f  "${CLAUDE_HOME}/agents/"*.md 2>/dev/null || true
    
    # Antigravity
    rm -f  "${ANTIGRAVITY_CONFIG}/GEMINI.md" 2>/dev/null || true
    rm -f  "${ANTIGRAVITY_CONFIG}/rules/pair-agent-core.md" 2>/dev/null || true
    rm -f  "${ANTIGRAVITY_CONFIG}/agents/"*.md 2>/dev/null || true

    # Common skills
    for skill in sprint-lifecycle agreement-document correction-record \
                 skill-learning retrospect vision-record \
                 project-start-empty project-start-existing vocabulary-capture project-init \
                 skill-survey; do
        rm -rf "${CLAUDE_HOME}/skills/${skill}" 2>/dev/null || true
        rm -rf "${ANTIGRAVITY_CONFIG}/skills/${skill}" 2>/dev/null || true
    done
    rm -f "${CLAUDE_HOME}/pair-agent/tools/skill-survey.py" 2>/dev/null || true  
    rm -f "${CLAUDE_HOME}/pair-agent/tools/emit_agents.py" 2>/dev/null || true
    rm -f "${CLAUDE_HOME}/pair-agent/tools/run_workflow.py" 2>/dev/null || true
    rm -f "${ANTIGRAVITY_CONFIG}/pair-agent/tools/"*.py 2>/dev/null || true

    # Restore CLAUDE.md backup if exists  
    if [[ -f "${CLAUDE_HOME}/CLAUDE.md.pair-agent-backup" ]]; then  
        mv "${CLAUDE_HOME}/CLAUDE.md.pair-agent-backup" "${CLAUDE_HOME}/CLAUDE.md"  
        info "Restored original CLAUDE.md from backup"  
    fi

    info "Uninstall complete."  
    exit 0  
fi

# --- Full install ---  
info "Installing Pair Agent to ~/.claude/ and ~/.gemini/config/ ..."

# Ensure directories (Claude)
mkdir -p "${CLAUDE_HOME}/rules"
mkdir -p "${CLAUDE_HOME}/skills"
mkdir -p "${CLAUDE_HOME}/agents"
mkdir -p "${CLAUDE_HOME}/pair-agent/skills"
mkdir -p "${CLAUDE_HOME}/pair-agent/vision"
mkdir -p "${CLAUDE_HOME}/pair-agent/corrections"
mkdir -p "${CLAUDE_HOME}/pair-agent/skill-library/pending"
mkdir -p "${CLAUDE_HOME}/pair-agent/skill-library/approved"
mkdir -p "${CLAUDE_HOME}/pair-agent/tools"

# Ensure directories (Antigravity)
mkdir -p "${ANTIGRAVITY_CONFIG}/rules"
mkdir -p "${ANTIGRAVITY_CONFIG}/skills"
mkdir -p "${ANTIGRAVITY_CONFIG}/agents"
mkdir -p "${ANTIGRAVITY_CONFIG}/pair-agent/skills"
mkdir -p "${ANTIGRAVITY_CONFIG}/pair-agent/vision"
mkdir -p "${ANTIGRAVITY_CONFIG}/pair-agent/corrections"
mkdir -p "${ANTIGRAVITY_CONFIG}/pair-agent/tools"

# Copy skill-survey config (only if not already customized)
if [[ ! -f "${CLAUDE_HOME}/pair-agent/skill-survey-config.json" ]]; then
    cp "${PAIR_AGENT_SRC}/pair-agent/skill-survey-config.json" "${CLAUDE_HOME}/pair-agent/"
    info "Installed pair-agent/skill-survey-config.json"
fi

# Copy tools
for tool in skill-survey.py survey-dev-prefs.py derive_roles.py simulate_mk.py check_skills.py check_report.py emit_claude.py emit_agents.py run_workflow.py deny_read.py measure_agent_usage.py; do
    if [[ -f "${SCRIPT_DIR}/tools/${tool}" ]]; then
        cp "${SCRIPT_DIR}/tools/${tool}" "${CLAUDE_HOME}/pair-agent/tools/"
        cp "${SCRIPT_DIR}/tools/${tool}" "${ANTIGRAVITY_CONFIG}/pair-agent/tools/"
    fi
done
info "Installed tools into ~/.claude/pair-agent/tools/ and ~/.gemini/config/pair-agent/tools/"

# Copy project template
if [[ -d "${PAIR_AGENT_SRC}/pair-agent/template" ]]; then  
    # Claude
    rm -rf "${CLAUDE_HOME}/pair-agent/template"  
    cp -r "${PAIR_AGENT_SRC}/pair-agent/template" "${CLAUDE_HOME}/pair-agent/template"  
    # Antigravity
    rm -rf "${ANTIGRAVITY_CONFIG}/pair-agent/template"
    cp -r "${PAIR_AGENT_SRC}/pair-agent/template" "${ANTIGRAVITY_CONFIG}/pair-agent/template"
    info "Installed pair-agent/template"  
fi

# Handle CLAUDE.md / GEMINI.md
if [[ -f "${CLAUDE_HOME}/CLAUDE.md" ]]; then  
    if ! grep -q "Pair Agent" "${CLAUDE_HOME}/CLAUDE.md" 2>/dev/null; then  
        cp "${CLAUDE_HOME}/CLAUDE.md" "${CLAUDE_HOME}/CLAUDE.md.pair-agent-backup"  
        echo "" >> "${CLAUDE_HOME}/CLAUDE.md"  
        echo "<!-- Pair Agent instructions appended below -->" >> "${CLAUDE_HOME}/CLAUDE.md"  
        cat "${PAIR_AGENT_SRC}/CLAUDE.md" >> "${CLAUDE_HOME}/CLAUDE.md"  
        info "Appended Pair Agent instructions to existing CLAUDE.md"  
    else  
        cp "${PAIR_AGENT_SRC}/CLAUDE.md" "${CLAUDE_HOME}/CLAUDE.md"  
        info "Updated CLAUDE.md"  
    fi  
else  
    cp "${PAIR_AGENT_SRC}/CLAUDE.md" "${CLAUDE_HOME}/CLAUDE.md"  
    info "Created CLAUDE.md"  
fi
# Copy to GEMINI.md
cp "${PAIR_AGENT_SRC}/GEMINI.md" "${ANTIGRAVITY_CONFIG}/GEMINI.md"
info "Created/Updated GEMINI.md in ~/.gemini/config/"

# Rules (Deploy to both)
cp "${PAIR_AGENT_SRC}/rules/pair-agent-core.md" "${CLAUDE_HOME}/rules/"  
cp "${PAIR_AGENT_SRC}/rules/pair-agent-core.md" "${ANTIGRAVITY_CONFIG}/rules/"  
info "Installed rules/pair-agent-core.md to Claude and Antigravity"

# Skills (Deploy to both)
for skill_dir in "${PAIR_AGENT_SRC}/skills/"*/; do  
    skill_name="$(basename "${skill_dir}")"  
    # Claude
    mkdir -p "${CLAUDE_HOME}/skills/${skill_name}"  
    cp "${skill_dir}SKILL.md" "${CLAUDE_HOME}/skills/${skill_name}/"  
    # Antigravity
    mkdir -p "${ANTIGRAVITY_CONFIG}/skills/${skill_name}"
    cp "${skill_dir}SKILL.md" "${ANTIGRAVITY_CONFIG}/skills/${skill_name}/"
    info "Installed skills/${skill_name}"  
done

# Agents (Deploy to both)
cp "${PAIR_AGENT_SRC}/agents/"*.md "${CLAUDE_HOME}/agents/"  
cp "${PAIR_AGENT_SRC}/agents/"*.md "${ANTIGRAVITY_CONFIG}/agents/"  
info "Installed agents (deliberation, retrospective, skill-executor) to Claude and Antigravity"

info ""  
info "Installation complete!"  
info ""  
info "Claude Code Home:       ~/.claude/"
info "Antigravity Config:     ~/.gemini/config/"
info ""  
info "To set up a project: cd your-project && ${SCRIPT_DIR}/install.sh --project"  
info "To start:            claude  (or  geminicli / antigravity)"
