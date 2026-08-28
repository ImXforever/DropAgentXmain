#!/usr/bin/env bash
# Hermes Marketplace — one-command VPS installer (Ubuntu 22/24)
set -e
echo "=== 1/4 Docker ==="
if ! command -v docker &>/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
docker compose version >/dev/null 2>&1 || { apt-get update && apt-get install -y docker-compose-plugin; }

echo "=== 2/4 App files ==="
mkdir -p /opt/hermes-marketplace && cd /opt/hermes-marketplace
[ -f docker-compose.yml ] || { echo "فایل‌های پروژه را در /opt/hermes-marketplace کپی کن (یا git clone)"; exit 1; }

echo "=== 3/4 .env ==="
if [ ! -f .env ]; then
  cp .env.example .env
  nano .env || vi .env   # BOT_TOKEN و ADMIN_IDS حداقل
fi

echo "=== 4/4 Build & Run ==="
mkdir -p data uploads
docker compose up -d --build
docker compose logs -f --tail 50
