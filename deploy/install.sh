#!/usr/bin/env bash
# Install reachy-mini-companion on a Reachy Mini robot.
#
# Usage:
#   ssh bedrock@reachy-mini.local
#   curl -fsSL https://raw.githubusercontent.com/awakia/reachy-video-chat/main/deploy/install.sh | bash
#
# Or from a local clone:
#   bash deploy/install.sh
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-$HOME/reachy-mini-companion}"
VENV_DIR="$INSTALL_DIR/.venv"
REPO_URL="https://github.com/awakia/reachy-video-chat.git"
CONFIG_DIR="$HOME/.reachy-mini-companion"
SERVICE_NAME="reachy-mini-companion"

echo "=== Reachy Mini AI Companion Installer ==="
echo ""

# ── 1. Clone or update repo ────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "[1/4] Updating existing installation..."
    cd "$INSTALL_DIR" && git pull --ff-only
else
    echo "[1/4] Cloning repository..."
    git clone "$REPO_URL" "$INSTALL_DIR"
    cd "$INSTALL_DIR"
fi

# ── 2. Create venv and install ─────────────────────────────────────
echo "[2/4] Installing Python dependencies..."
python3 -m venv "$VENV_DIR"
"$VENV_DIR/bin/pip" install --quiet --upgrade pip
"$VENV_DIR/bin/pip" install --quiet -e ".[all]"

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
    echo "[3/4] API key already configured."
fi

# ── 4. Install systemd service ────────────────────────────────────
echo "[4/4] Setting up systemd service..."

CURRENT_USER="$(whoami)"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

sudo tee "$SERVICE_FILE" > /dev/null <<UNIT
[Unit]
Description=Reachy Mini AI Companion
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${CURRENT_USER}
WorkingDirectory=${INSTALL_DIR}
ExecStart=${VENV_DIR}/bin/reachy-mini-companion
Restart=on-failure
RestartSec=10
Environment=HOME=/home/${CURRENT_USER}

[Install]
WantedBy=multi-user.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
sudo systemctl restart "$SERVICE_NAME"

echo ""
echo "=== Installation complete! ==="
echo ""
echo "  Status:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    journalctl -u $SERVICE_NAME -f"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "  Config:  $CONFIG_DIR/.env"
echo ""
