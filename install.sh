#!/usr/bin/env bash  
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"  
CLAUDE_HOME="${HOME}/.claude"  
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
        cp -r "${PROJECT_TEMPLATE}/.pair-agent" .  
        info "Created .pair-agent/ in $(pwd)"  
        info "Add to .gitignore if needed: .pair-agent/current-sprint.json"  
    fi  
    exit 0  
fi

# --- Uninstall ---  
if [[ "${1:-}" == "--uninstall" ]]; then  
    warn "Removing Pair Agent files from ~/.claude/ ..."  
    warn "(~/.claude/pair-agent/ learning data is preserved)"

    rm -f  "${CLAUDE_HOME}/CLAUDE.md.pair-agent-backup" 2>/dev/null || true  
    # Remove rules  
    rm -f  "${CLAUDE_HOME}/rules/pair-agent-core.md" 2>/dev/null || true  
    # Remove skills  
    for skill in sprint-lifecycle agreement-document correction-record \
                 skill-learning retrospect vision-record \
                 project-start-empty project-start-existing vocabulary-capture; do  
        rm -rf "${CLAUDE_HOME}/skills/${skill}" 2>/dev/null || true  
    done  
    # Remove agents  
    for agent in deliberation.md retrospective.md skill-executor.md; do  
        rm -f "${CLAUDE_HOME}/agents/${agent}" 2>/dev/null || true  
    done

    # Restore CLAUDE.md backup if exists  
    if [[ -f "${CLAUDE_HOME}/CLAUDE.md.pair-agent-backup" ]]; then  
        mv "${CLAUDE_HOME}/CLAUDE.md.pair-agent-backup" "${CLAUDE_HOME}/CLAUDE.md"  
        info "Restored original CLAUDE.md from backup"  
    fi

    info "Uninstall complete. Learning data in ~/.claude/pair-agent/ preserved."  
    exit 0  
fi

# --- Full install ---  
info "Installing Pair Agent to ~/.claude/ ..."

# Ensure directories  
mkdir -p "${CLAUDE_HOME}/rules"  
mkdir -p "${CLAUDE_HOME}/skills"  
mkdir -p "${CLAUDE_HOME}/agents"  
mkdir -p "${CLAUDE_HOME}/pair-agent/skills"  
mkdir -p "${CLAUDE_HOME}/pair-agent/vision"  
mkdir -p "${CLAUDE_HOME}/pair-agent/corrections"

# Backup existing CLAUDE.md  
if [[ -f "${CLAUDE_HOME}/CLAUDE.md" ]]; then  
    if ! grep -q "Pair Agent" "${CLAUDE_HOME}/CLAUDE.md" 2>/dev/null; then  
        cp "${CLAUDE_HOME}/CLAUDE.md" "${CLAUDE_HOME}/CLAUDE.md.pair-agent-backup"  
        warn "Backed up existing CLAUDE.md to CLAUDE.md.pair-agent-backup"  
        # Append pair-agent content  
        echo "" >> "${CLAUDE_HOME}/CLAUDE.md"  
        echo "<!-- Pair Agent instructions appended below -->" >> "${CLAUDE_HOME}/CLAUDE.md"  
        cat "${PAIR_AGENT_SRC}/CLAUDE.md" >> "${CLAUDE_HOME}/CLAUDE.md"  
        info "Appended Pair Agent instructions to existing CLAUDE.md"  
    else  
        cp "${PAIR_AGENT_SRC}/CLAUDE.md" "${CLAUDE_HOME}/CLAUDE.md"  
        info "Updated CLAUDE.md (Pair Agent content already present)"  
    fi  
else  
    cp "${PAIR_AGENT_SRC}/CLAUDE.md" "${CLAUDE_HOME}/CLAUDE.md"  
    info "Created CLAUDE.md"  
fi

# Rules  
cp "${PAIR_AGENT_SRC}/rules/pair-agent-core.md" "${CLAUDE_HOME}/rules/"  
info "Installed rules/pair-agent-core.md"

# Skills  
for skill_dir in "${PAIR_AGENT_SRC}/skills/"*/; do  
    skill_name="$(basename "${skill_dir}")"  
    mkdir -p "${CLAUDE_HOME}/skills/${skill_name}"  
    cp "${skill_dir}SKILL.md" "${CLAUDE_HOME}/skills/${skill_name}/"  
    info "Installed skills/${skill_name}"  
done

# Agents  
cp "${PAIR_AGENT_SRC}/agents/"*.md "${CLAUDE_HOME}/agents/"  
info "Installed agents (deliberation, retrospective, skill-executor)"

info ""  
info "Installation complete!"  
info ""  
info "Learning data directory: ~/.claude/pair-agent/"  
info "  skills/      — 師匠の判断基準（プロジェクトを跨ぐ）"  
info "  vision/      — ビジョン記録"  
info "  corrections/  — 叱責・修正記録"  
info ""  
info "To set up a project: cd your-project && ${SCRIPT_DIR}/install.sh --project"  
info "To start: claude"
