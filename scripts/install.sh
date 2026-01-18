#!/usr/bin/env bash

# Mistral Vibe Installation Script
# This script installs uv if not present and then installs mistral-vibe using uv

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

function check_platform() {
    local platform=$(uname -s)

    if [[ "$platform" == "Linux" ]]; then
        info "Detected Linux platform"
        PLATFORM="linux"
    elif [[ "$platform" == "Darwin" ]]; then
        info "Detected macOS platform"
        PLATFORM="macos"
    else
        error "Unsupported platform: $platform"
        error "This installation script currently only supports Linux and macOS"
        exit 1
    fi
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

        export PATH="$HOME/.local/bin:$PATH"

        if ! command -v uv &> /dev/null; then
            warning "uv was installed but not found in PATH for this session"
            warning "You may need to restart your terminal or run:"
            warning "  export PATH=\"\$HOME/.cargo/bin:\$HOME/.local/bin:\$PATH\""
        fi
    else
        error "Failed to install uv"
        exit 1
    fi
}

INSTALL_ROOT=${INSTALL_ROOT:-/bin/porker-vibe}
ENTRY_POINTS=("vibe" "vibe-acp")
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL_TEMP_DIR=""

function run_privileged() {
    if [[ $(id -u) -eq 0 ]]; then
        "$@"
        return
    fi

    if command -v sudo &> /dev/null; then
        sudo "$@"
    else
        error "Root privileges are required to run: $*"
        error "Please rerun this script with sudo or as root."
        exit 1
    fi
}

function install_vibe() {
    info "Installing mistral-vibe into ${INSTALL_ROOT}..."

    INSTALL_TEMP_DIR=$(mktemp -d)
    trap '[[ -n "${INSTALL_TEMP_DIR}" ]] && rm -rf "${INSTALL_TEMP_DIR}"' EXIT

    uv run pip install --prefix "${INSTALL_TEMP_DIR}" "${REPO_ROOT}"

    run_privileged rm -rf "${INSTALL_ROOT}" 2>/dev/null || true
    run_privileged mkdir -p "${INSTALL_ROOT}"
    run_privileged cp -R "${INSTALL_TEMP_DIR}/." "${INSTALL_ROOT}/"

    for entry in "${ENTRY_POINTS[@]}"; do
        local target="${INSTALL_ROOT}/bin/${entry}"
        if [[ -f "${target}" ]]; then
            run_privileged ln -sf "${target}" "/bin/${entry}"
        fi
    done

    success "Mistral Vibe installed successfully in ${INSTALL_ROOT} (commands: /bin/vibe, /bin/vibe-acp)"
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
    echo "Starting Mistral Vibe installation..."
    echo

    check_platform

    check_uv_installed

    if [[ "$UV_INSTALLED" == "false" ]]; then
        install_uv
    fi

    install_vibe

    if command -v vibe &> /dev/null; then
        success "Installation completed successfully!"
        echo
        echo "You can now run vibe with:"
        echo "  vibe"
        echo
        echo "Or for ACP mode:"
        echo "  vibe-acp"
    else
        error "Installation completed but 'vibe' command not found"
        error "Please check your installation and PATH settings"
        exit 1
    fi
}

main
