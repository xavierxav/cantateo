#!/bin/bash
# Initial server setup script for Cantateo on Hetzner
# Run as root on a fresh Ubuntu 22.04 server
# Usage: bash setup-server.sh

set -e

echo "=== Cantateo Server Setup ==="

# Update system
echo "[1/10] Updating system..."
apt update && apt upgrade -y

# Install dependencies
echo "[2/10] Installing dependencies..."
apt install -y \
    python3-venv \
    python3-pip \
    python3-dev \
    postgresql \
    postgresql-contrib \
    redis-server \
    nginx \
    certbot \
    python3-certbot-dns-cloudflare \
    git \
    build-essential \
    libpq-dev \
    fluidsynth \
    ffmpeg \
    poppler-utils \
    ufw

# Create application user
echo "[3/10] Creating application user..."
if ! id "cantateo" &>/dev/null; then
    adduser --disabled-password --gecos "" cantateo
    echo "User 'cantateo' created"
else
    echo "User 'cantateo' already exists"
fi

# Setup firewall
echo "[4/10] Configuring firewall..."
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# Setup PostgreSQL
echo "[5/10] Setting up PostgreSQL..."
sudo -u postgres psql -c "CREATE USER cantateo WITH PASSWORD 'CHANGE_THIS_PASSWORD';" 2>/dev/null || echo "User already exists"
sudo -u postgres psql -c "CREATE DATABASE cantateo OWNER cantateo;" 2>/dev/null || echo "Database already exists"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE cantateo TO cantateo;"

# Enable services
echo "[6/10] Enabling services..."
systemctl enable postgresql
systemctl enable redis-server
systemctl enable nginx

# Create application directory
echo "[7/10] Creating application directory..."
mkdir -p /var/www/cantateo
chown cantateo:cantateo /var/www/cantateo

# Create log directory
echo "[8/10] Creating log directory..."
mkdir -p /var/log/cantateo
chown cantateo:cantateo /var/log/cantateo

# Create backup directory
echo "[9/10] Creating backup directory..."
mkdir -p /var/backups/cantateo
chown cantateo:cantateo /var/backups/cantateo

# Install and enable systemd services (execute, never just print —
# a previously echoed instruction was skipped and left cantateo.service
# disabled at boot)
if [ -f deploy/cantateo.service ]; then
    echo "[10/10] Installing systemd services..."
    cp deploy/cantateo.service /etc/systemd/system/
    cp deploy/cantateo-worker.service /etc/systemd/system/
    cp deploy/cantateo-omr-worker.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable cantateo cantateo-worker cantateo-omr-worker
else
    echo "[10/10] deploy/cantateo.service not found — run this script from the repository root"
fi

echo "[10/10] Setup complete!"
echo ""
echo "=== Next Steps ==="
echo "1. Clone your repository:"
echo "   su - cantateo"
echo "   cd /var/www/cantateo"
echo "   git clone <YOUR_REPO_URL> ."
echo ""
echo "2. Create virtual environment:"
echo "   python3 -m venv venv"
echo "   source venv/bin/activate"
echo "   pip install -r requirements.txt"
echo ""
echo "3. Create .env file:"
echo "   cp .env.example .env"
echo "   nano .env  # Edit with your values"
echo ""
echo "4. Run migrations:"
echo "   python manage.py migrate"
echo "   python manage.py collectstatic --no-input"
echo ""
echo "5. Systemd services: already installed and enabled by this script"
echo "   (verify with: systemctl status cantateo)"
echo ""
echo "6. Configure Nginx:"
echo "   sudo cp deploy/nginx.conf /etc/nginx/sites-available/cantateo"
echo "   sudo ln -s /etc/nginx/sites-available/cantateo /etc/nginx/sites-enabled/"
echo "   sudo rm /etc/nginx/sites-enabled/default"
echo "   sudo nginx -t"
echo "   sudo systemctl reload nginx"
echo ""
echo "7. Get SSL certificate (DNS-01 via Cloudflare):"
echo "   sudo mkdir -p /etc/letsencrypt"
echo "   sudo nano /etc/letsencrypt/cloudflare.ini  # dns_cloudflare_api_token = <your_token>"
echo "   sudo chmod 600 /etc/letsencrypt/cloudflare.ini"
echo "   sudo certbot certonly --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini -d cantateo.fr -d www.cantateo.fr"
echo "   sudo certbot certonly --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini -d beta.cantateo.fr"
echo "   sudo certbot certonly --dns-cloudflare --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini -d cancionero.cantateo.fr"
echo ""
echo "8. IMPORTANT: Change the PostgreSQL password!"
echo "   sudo -u postgres psql"
echo "   ALTER USER cantateo WITH PASSWORD 'your-secure-password';"
echo ""
echo "=== Setup Complete ==="
