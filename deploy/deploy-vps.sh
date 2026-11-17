#!/usr/bin/env bash
set -euo pipefail

# ========================================================
# Temuan Harian Automated VPS Deployment Script
# Target Host: 43.134.26.73 (Ubuntu)
# Domain: temuan-harian.pdfumi.com (Host Port: 8005)
# ========================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$ROOT_DIR"

echo "=================================================="
echo "🚀 Starting Temuan Harian Deployment on VPS"
echo "Working directory: $ROOT_DIR"
echo "=================================================="

# 1. Pastikan .env tersedia
if [ ! -f .env ]; then
  if [ -f .env.production ]; then
    echo "⚙️ Creating .env from .env.production..."
    cp .env.production .env
  else
    echo "⚙️ Creating .env from .env.example..."
    cp .env.example .env
  fi
  echo "✅ .env initialized."
else
  echo "✅ .env file already exists."
fi

# 2. Build dan jalankan Docker Compose
echo "🐳 Building and starting Docker containers (Port 8005 -> 8000)..."
docker compose down || true
docker compose up -d --build

# 3. Tunggu kontainer & verifikasi port
echo "⏳ Verifying services status..."
sleep 5
docker compose ps

echo "🔍 Testing Web Dashboard (port 8005)..."
curl -s -I http://127.0.0.1:8005 | head -n 1 || echo "⚠️ Port 8005 warming up..."

# 4. Setup Nginx Reverse Proxy
echo "🌐 Configuring Nginx Reverse Proxy for temuan-harian.pdfumi.com..."
if [ -d /etc/nginx/sites-available ]; then
  sudo cp deploy/nginx-temuan-harian.pdfumi.com.conf /etc/nginx/sites-available/temuan-harian.pdfumi.com
  sudo ln -sf /etc/nginx/sites-available/temuan-harian.pdfumi.com /etc/nginx/sites-enabled/
  if sudo nginx -t; then
    sudo systemctl reload nginx
    echo "✅ Nginx reloaded successfully."
  else
    echo "⚠️ Nginx test failed. Please check config."
  fi
fi

echo ""
echo "=================================================="
echo "🎉 Temuan Harian Deployed Successfully!"
echo "• Local Container URL: http://127.0.0.1:8005"
echo "• Public Domain:       https://temuan-harian.pdfumi.com"
echo ""
echo "📋 To obtain/renew SSL certificate:"
echo "sudo certbot --nginx -d temuan-harian.pdfumi.com"
echo "=================================================="
