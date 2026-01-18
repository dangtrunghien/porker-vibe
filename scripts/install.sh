#!/usr/bin/env bash

# Mistral Vibe Installation Script (Virtual Environment with Global Launcher)
# This script installs uv if not present, sets up a virtual environment,
# installs vibe into it, and creates a global launcher script.

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

function error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

function info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

function success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

function warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

function check_uv_installed() {
    if command -v uv &> /dev/null; then
        info "uv is already installed: $(uv --version)"
        UV_INSTALLED=true
    else
        info "uv is not installed"
        UV_INSTALLED=false
    fi
}

function install_uv() {
    info "Installing uv using the official Astral installer..."

    if ! command -v curl &> /dev/null; then
        error "curl is required to install uv. Please install curl first."
        exit 1
    fi

    if curl -LsSf https://astral.sh/uv/install.sh | sh; then
        success "uv installed successfully"

        # Ensure uv is in PATH for the current session
        export PATH="$HOME/.cargo/bin:$PATH"
        export PATH="$HOME/.local/bin:$PATH"

        if ! command -v uv &> /dev/null; then
            warning "uv was installed but not found in PATH for this session."
            warning "You may need to restart your terminal or manually add:"
            warning "  export PATH=\"$HOME/.cargo/bin:\$HOME/.local/bin:\$PATH\""
        fi
    else
        error "Failed to install uv"
        exit 1
    fi
}

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="${REPO_ROOT}/.venv"
LAUNCHER_BIN_DIR="$HOME/.local/bin"
LAUNCHER_PATH="${LAUNCHER_BIN_DIR}/vibe"

function setup_virtual_environment() {
    info "Setting up virtual environment in ${VENV_DIR}..."

    if [ -d "${VENV_DIR}" ]; then
        info "Existing virtual environment found. Removing and recreating..."
        rm -rf "${VENV_DIR}"
    fi

    uv venv --python "$(cat "${REPO_ROOT}/.python-version")" "${VENV_DIR}"
    source "${VENV_DIR}/bin/activate"

    info "Installing vibe into the virtual environment..."
    uv pip install -e "${REPO_ROOT}"

    success "Virtual environment set up and vibe installed successfully."
}

function create_global_launcher() {
    info "Creating global 'vibe' launcher script in ${LAUNCHER_BIN_DIR}..."

    mkdir -p "${LAUNCHER_BIN_DIR}"

    cat << EOF > "${LAUNCHER_PATH}"
#!/usr/bin/env bash
# Vibe Launcher Script
# This script activates the project's virtual environment and runs vibe.

# Path to the project root (where the .venv is located)
PROJECT_ROOT="${REPO_ROOT}"
# Path to the virtual environment's activate script
VENV_ACTIVATE="\${PROJECT_ROOT}/.venv/bin/activate"
VENV_VIBE_EXECUTABLE="\${PROJECT_ROOT}/.venv/bin/vibe"

if [ -f "\${VENV_ACTIVATE}" ]; then
    source "\${VENV_ACTIVATE}"
    exec "\${VENV_VIBE_EXECUTABLE}" "\$@"
else
    echo "Error: Virtual environment not found at \${PROJECT_ROOT}. Please re-run the install script." >&2
    exit 1
fi
EOF

    chmod +x "${LAUNCHER_PATH}"
    success "Global launcher script created at ${LAUNCHER_PATH}."
}

function check_path_and_inform() {
    if [[ ":$PATH:" != ":${LAUNCHER_BIN_DIR}:" ]]; then
        warning "${LAUNCHER_BIN_DIR} is not in your system's PATH."
        warning "To run 'vibe' directly, you need to add it to your PATH."
        warning "You can do this by adding the following line to your shell's config file (e.g., ~/.bashrc or ~/.zshrc):"
        warning "  export PATH=\"$HOME/.local/bin:\$PATH\""
        warning "Then restart your terminal or run 'source ~/.bashrc' (or ~/.zshrc)."
    else
        info "${LAUNCHER_BIN_DIR} is already in your PATH. You should be able to run 'vibe' directly."
    fi
}

function main() {
    echo
    echo "██████████████████░░"
    echo "██████████████████░░"
    echo "████  ██████  ████░░"
    echo "████    ██    ████░░"
    echo "████          ████░░"
    echo "████  ██  ██  ████░░"
    echo "██      ██      ██░░"
    echo "██████████████████░░"
    echo "██████████████████░░"
    echo
    echo "Starting Mistral Vibe installation with virtual environment and global launcher..."
    echo

    check_uv_installed
    if [[ "$UV_INSTALLED" == "false" ]]; then
        install_uv
    fi

    setup_virtual_environment
    create_global_launcher
    check_path_and_inform

    success "Installation completed successfully!"
    echo
    echo "You should now be able to run 'vibe' directly from your terminal."
    echo
}

main
