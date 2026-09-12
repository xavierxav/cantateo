#!/bin/bash
# Deployment script for Cantateo on Hetzner
# Usage: ssh root@5.75.146.72 'su - cantateo -c /var/www/cantateo/deploy/deploy.sh'
# Or: ssh root@5.75.146.72 '/var/www/cantateo/deploy/deploy.sh' (if running as root)

set -e

APP_DIR="/var/www/cantateo"
VENV="$APP_DIR/venv"

echo "=== Cantateo Deployment ==="

# If running as root, re-run the script as cantateo user
if [ "$(whoami)" = "root" ]; then
    echo "Switching to cantateo user..."
    exec su - cantateo -c "bash '$APP_DIR/deploy/deploy.sh'"
fi

# Navigate to app directory
cd "$APP_DIR"

# Check for required system dependencies
echo "[0/6] Checking system dependencies..."
if ! command -v ffmpeg &> /dev/null; then
    echo "❌ FFmpeg not found. Install with: apt install ffmpeg -y"
    exit 1
fi
if ! command -v ffprobe &> /dev/null; then
    echo "❌ FFprobe not found. Install with: apt install ffmpeg -y"
    exit 1
fi
if ! command -v fluidsynth &> /dev/null; then
    echo "❌ FluidSynth not found. Install with: apt install fluidsynth -y"
    exit 1
fi
if ! command -v pdftoppm &> /dev/null || ! command -v pdfinfo &> /dev/null; then
    echo "❌ Poppler tools not found. Install with: apt install poppler-utils -y"
    exit 1
fi
echo "✓ FFmpeg, FFprobe, FluidSynth and Poppler found"

# Pull latest changes
echo "[1/6] Pulling latest changes..."
git pull origin master

# Activate virtual environment
echo "[2/6] Activating virtual environment..."
[ -d "$VENV" ] || python3 -m venv "$VENV"
source "$VENV/bin/activate"

# Install/update dependencies
echo "[3/6] Installing dependencies..."
pip install -r requirements.txt -c requirements-lock.txt --quiet

# Run migrations
echo "[4/6] Checking and running migrations..."
if ! python manage.py migrate --check --no-input; then
    echo "Pending migrations detected; applying them now."
fi
python manage.py migrate --no-input

# Collect static files
echo "[5/6] Collecting static files..."
python manage.py collectstatic --no-input --clear

# Add FFmpeg path to environment if not already set
if [ -f "$APP_DIR/.env" ] && ! grep -q "FFMPEG_PATH" "$APP_DIR/.env"; then
    echo "[*] Adding FFMPEG_PATH to .env..."
    FFMPEG_BIN=$(which ffmpeg)
    [ -n "$FFMPEG_BIN" ] && echo "FFMPEG_PATH=$FFMPEG_BIN" >> "$APP_DIR/.env"
fi
if [ -f "$APP_DIR/.env" ] && ! grep -q "FFPROBE_PATH" "$APP_DIR/.env"; then
    echo "[*] Adding FFPROBE_PATH to .env..."
    FFPROBE_BIN=$(which ffprobe)
    [ -n "$FFPROBE_BIN" ] && echo "FFPROBE_PATH=$FFPROBE_BIN" >> "$APP_DIR/.env"
fi

# Install optional systemd units that need daemon-reload when changed
echo "[6/7] Installing systemd units..."
if command -v systemctl &> /dev/null; then
    if sudo -n install -m 0644 "$APP_DIR/deploy/cantateo-worker.service" /etc/systemd/system/cantateo-worker.service \
        && sudo -n install -m 0644 "$APP_DIR/deploy/cantateo-omr-worker.service" /etc/systemd/system/cantateo-omr-worker.service \
        && sudo -n install -m 0644 "$APP_DIR/deploy/cantateo-audio-backfill.service" /etc/systemd/system/cantateo-audio-backfill.service \
        && sudo -n install -m 0644 "$APP_DIR/deploy/cantateo-audio-backfill.timer" /etc/systemd/system/cantateo-audio-backfill.timer; then
        sudo systemctl daemon-reload
        sudo systemctl enable --now cantateo-audio-backfill.timer || true
    else
        echo "⚠️ Could not install worker/backfill systemd units automatically."
    fi
fi

# Restart services
echo "[7/7] Restarting service..."
# Always use sudo for systemctl as we are now guaranteed to be cantateo user
sudo systemctl restart cantateo
sudo systemctl restart cantateo-worker || true
sudo systemctl restart cantateo-omr-worker || true

echo "=== Deployment complete ==="
echo "Check status with: systemctl status cantateo"
echo "Check worker with: systemctl status cantateo-worker"
echo "Check OMR worker with: systemctl status cantateo-omr-worker"
echo "View logs with: journalctl -u cantateo -f"
