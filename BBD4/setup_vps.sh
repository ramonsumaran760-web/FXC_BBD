#!/bin/bash
# deploy/setup_vps.sh — Script de deploy completo en VPS Ubuntu 22.04
# Uso: bash setup_vps.sh tu-dominio.com

DOMAIN=${1:-"investiq.com"}
APP_DIR="/opt/investiq"
USER="investiq"

echo "╔══════════════════════════════════════════════════╗"
echo "║     InvestIQ — Deploy VPS Ubuntu 22.04          ║"
echo "╚══════════════════════════════════════════════════╝"

# 1. Sistema base
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq curl git nginx certbot python3-certbot-nginx \
    build-essential libpq-dev python3.12 python3.12-venv python3-pip \
    postgresql-15 redis-server supervisor ufw

# 2. PostgreSQL + TimescaleDB
echo "Configurando PostgreSQL..."
sudo -u postgres psql -c "CREATE USER investiq WITH PASSWORD 'InvestIQ2026Prod!';"
sudo -u postgres psql -c "CREATE DATABASE investiq OWNER investiq;"
sudo -u postgres psql -c "GRANT ALL ON DATABASE investiq TO investiq;"
# Instalar TimescaleDB
curl -fsSL https://packagecloud.io/timescale/timescaledb/gpgkey | gpg --dearmor > /etc/apt/trusted.gpg.d/timescaledb.gpg
echo "deb https://packagecloud.io/timescale/timescaledb/debian/ bookworm main" > /etc/apt/sources.list.d/timescaledb.list
apt-get update -qq && apt-get install -y timescaledb-2-postgresql-15
timescaledb-tune --quiet --yes
systemctl restart postgresql

# 3. Redis con password
sed -i 's/# requirepass foobared/requirepass InvestIQRedis2026!/' /etc/redis/redis.conf
sed -i 's/bind 127.0.0.1 -::1/bind 127.0.0.1/' /etc/redis/redis.conf
systemctl restart redis-server

# 4. App Python
useradd -m -s /bin/bash $USER 2>/dev/null || true
mkdir -p $APP_DIR
cd $APP_DIR
python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip -q
pip install -r /tmp/requirements.txt -q

# 5. Variables entorno
cat > $APP_DIR/.env << ENV
DATABASE_URL=postgresql+asyncpg://investiq:InvestIQ2026Prod!@localhost:5432/investiq
DATABASE_URL_SYNC=postgresql://investiq:InvestIQ2026Prod!@localhost:5432/investiq
REDIS_URL=redis://:InvestIQRedis2026!@localhost:6379/0
SECRET_KEY=$(openssl rand -hex 32)
ALPACA_API_KEY=${ALPACA_API_KEY:-DEMO_KEY}
ALPACA_API_SECRET=${ALPACA_API_SECRET:-DEMO_SECRET}
CLAUDE_API_KEY=${CLAUDE_API_KEY:-}
STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY:-}
STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET:-}
MERCADOPAGO_ACCESS_TOKEN=${MERCADOPAGO_ACCESS_TOKEN:-}
APP_URL=https://$DOMAIN
ENV

# 6. Supervisor (proceso manager)
cat > /etc/supervisor/conf.d/investiq.conf << SUPERVISOR
[program:investiq]
command=$APP_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 4
directory=$APP_DIR/backend
user=$USER
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/investiq.log
environment=PATH="$APP_DIR/venv/bin"
SUPERVISOR
supervisorctl reread && supervisorctl update && supervisorctl start investiq

# 7. Nginx
cat > /etc/nginx/sites-available/investiq << NGINX
upstream backend { server 127.0.0.1:8000; keepalive 32; }
server {
    listen 80;
    server_name $DOMAIN www.$DOMAIN;
    return 301 https://\$host\$request_uri;
}
server {
    listen 443 ssl http2;
    server_name $DOMAIN www.$DOMAIN;
    ssl_certificate /etc/letsencrypt/live/$DOMAIN/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/$DOMAIN/privkey.pem;
    ssl_protocols TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    client_max_body_size 10M;
    location /api/ { proxy_pass http://backend; proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr; proxy_read_timeout 120s; }
    location /ws { proxy_pass http://backend; proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade; proxy_set_header Connection "upgrade";
        proxy_set_header Host \$host; proxy_read_timeout 86400s; }
    location / { root /opt/investiq/frontend/build; try_files \$uri /index.html; }
    location /static/ { proxy_pass http://backend; expires 1h; }
}
NGINX
ln -sf /etc/nginx/sites-available/investiq /etc/nginx/sites-enabled/
certbot --nginx -d $DOMAIN -d www.$DOMAIN --non-interactive --agree-tos -m admin@$DOMAIN
nginx -t && systemctl reload nginx

# 8. Firewall
ufw allow OpenSSH && ufw allow 'Nginx Full' && ufw --force enable

echo ""
echo "✅ Deploy completo en https://$DOMAIN"
echo "   Logs: tail -f /var/log/investiq.log"
echo "   Restart: supervisorctl restart investiq"

# ── Backups automáticos con cron ──────────────────────────
echo "Configurando backups automáticos..."

# Script de backup
cat > /opt/investiq/backup.sh << 'BACKUP'
#!/bin/bash
cd /opt/investiq/backend
source /opt/investiq/venv/bin/activate
python3 workers/backup_worker.py diario >> /var/log/investiq_backup.log 2>&1
BACKUP
chmod +x /opt/investiq/backup.sh

# Crontab: backup diario a las 2am + semanal domingo 3am
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/investiq/backup.sh") | crontab -
(crontab -l 2>/dev/null; echo "0 3 * * 0 cd /opt/investiq/backend && source /opt/investiq/venv/bin/activate && python3 workers/backup_worker.py semanal >> /var/log/investiq_backup.log 2>&1") | crontab -

echo "✓ Backups configurados: diario 2am + semanal domingo 3am"
echo "  Logs: tail -f /var/log/investiq_backup.log"
echo ""

# ── Sentry DSN en .env ────────────────────────────────────
if [ -n "${SENTRY_DSN}" ]; then
    echo "SENTRY_DSN=${SENTRY_DSN}" >> /opt/investiq/.env
    echo "✓ Sentry DSN configurado"
else
    echo "  (opcional) Agregar SENTRY_DSN en /opt/investiq/.env para monitoreo"
fi

# ── Stripe keys ───────────────────────────────────────────
if [ -n "${STRIPE_SECRET_KEY}" ]; then
    echo "STRIPE_SECRET_KEY=${STRIPE_SECRET_KEY}" >> /opt/investiq/.env
    echo "STRIPE_PUBLISHABLE_KEY=${STRIPE_PUBLISHABLE_KEY}" >> /opt/investiq/.env
    echo "STRIPE_WEBHOOK_SECRET=${STRIPE_WEBHOOK_SECRET}" >> /opt/investiq/.env
    echo "✓ Stripe configurado"
fi

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║  Deploy completo. Variables pendientes en .env:     ║"
echo "║  ALPACA_API_KEY    → app.alpaca.markets (gratis)   ║"
echo "║  CLAUDE_API_KEY    → console.anthropic.com         ║"
echo "║  STRIPE_SECRET_KEY → dashboard.stripe.com          ║"
echo "║  MERCADOPAGO_*     → mercadopago.com/developers    ║"
echo "║  SENTRY_DSN        → sentry.io (gratis tier)       ║"
echo "║  BACKUP_S3_BUCKET  → aws.amazon.com/s3 (opcional)  ║"
echo "╚══════════════════════════════════════════════════════╝"
