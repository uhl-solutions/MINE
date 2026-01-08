#!/bin/bash
# Install MINE skills (macOS / Linux wrapper)
# Usage: ./install.sh [options]
# Remote Usage: curl -fsSL https://raw.githubusercontent.com/uhl-solutions/MINE/main/scripts/install.sh | bash

set -e

# --- 1. Environment Setup ---
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    if command -v python &> /dev/null; then
        if python --version 2>&1 | grep -q "Python 3"; then
            PYTHON_CMD="python"
        else
            echo "Error: Python 3 is required."
            exit 1
        fi
    else
        echo "Error: Python 3 not found. Please install Python 3.9+."
        exit 1
    fi
fi

# --- 2. Locate Installer ---
# Try to find install_skills.py relative to this script or current directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
INSTALLER_PATH=""

if [ -f "$SCRIPT_DIR/install_skills.py" ]; then
    INSTALLER_PATH="$SCRIPT_DIR/install_skills.py"
elif [ -f "./scripts/install_skills.py" ]; then
    INSTALLER_PATH="./scripts/install_skills.py"
elif [ -f "./install_skills.py" ]; then
    INSTALLER_PATH="./install_skills.py"
fi

# --- 3. Execute ---
if [ -n "$INSTALLER_PATH" ]; then
    # LOCAL MODE: Run the found installer
    "$PYTHON_CMD" "$INSTALLER_PATH" "$@"
else
    # REMOTE MODE: Clone and run
    echo "Installer not found locally. Downloading from GitHub..."
    
    if ! command -v git &> /dev/null; then
        echo "Error: git is required for remote installation."
        exit 1
    fi

    TEMP_DIR=$(mktemp -d)
    cleanup() {
        rm -rf "$TEMP_DIR"
    }
    trap cleanup EXIT

    echo "Cloning MINE repository to temporary directory..."
    git clone --depth 1 https://github.com/uhl-solutions/MINE.git "$TEMP_DIR/mine" > /dev/null
    
    echo "Running installer..."
    "$PYTHON_CMD" "$TEMP_DIR/mine/scripts/install_skills.py" "$@" --source-root "$TEMP_DIR/mine"
fi
