#!/usr/bin/env bash
# Install reachy-mini-companion on a Reachy Mini robot.
#
# The Reachy Mini daemon discovers apps via entry points in /venvs/apps_venv/.
# This script installs the companion into that shared venv so it appears in the
# dashboard's Applications list and can be started with one click.
#
# Usage:
#   ssh pollen@reachy-mini.local  (password: root)
#   curl -fsSL https://raw.githubusercontent.com/awakia/reachy-video-chat/main/deploy/install.sh | bash
#
# Or from a local clone:
#   bash deploy/install.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/reachy-mini-companion}"
APPS_VENV="/venvs/apps_venv"
REPO_URL="https://github.com/awakia/reachy-video-chat.git"
CONFIG_DIR="$HOME/.reachy-mini-companion"

echo "=== Reachy Mini AI Companion Installer ==="
echo ""

# ── 1. Clone or update repo ────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "[1/3] Updating existing installation..."
    cd "$INSTALL_DIR" && git pull --ff-only
else
    echo "[1/3] Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── 2. Install into the daemon's shared apps venv ─────────────────
echo "[2/3] Installing into apps venv ($APPS_VENV)..."
if [ ! -d "$APPS_VENV" ]; then
    echo "ERROR: $APPS_VENV not found. Is this a Reachy Mini with the daemon installed?"
    exit 1
fi
"$APPS_VENV/bin/pip" install --quiet -e "."

# ── 3. Configure API key ──────────────────────────────────────────
mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/.env" ]; then
    echo ""
    echo "No API key found. Get one at: https://aistudio.google.com/apikey"
    read -rp "Enter your Google Gemini API key: " api_key
    echo "GOOGLE_API_KEY=$api_key" > "$CONFIG_DIR/.env"
    chmod 600 "$CONFIG_DIR/.env"
    echo "API key saved to $CONFIG_DIR/.env"
else
    echo "[3/3] API key already configured."
fi

echo ""
echo "=== Installation complete! ==="
echo ""
echo "  The app should now appear in the Reachy Mini dashboard."
echo "  If not, restart the daemon:  sudo systemctl restart reachy-mini-daemon"
echo ""
echo "  Config:  $CONFIG_DIR/.env"
echo ""
