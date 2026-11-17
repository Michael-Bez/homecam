#!/usr/bin/env bash
# Deploy from dev PC to Pi over SSH. Only use from dev PC if you do not plan to work straight from Pi.
# Prerequisites: SSH key auth working (ssh michael@homecam succeeds without password)
# and rsync installed locally (Git Bash on Windows does not ship with it).
#
# Usage:  ./scripts/deploy.sh

set -euo pipefail

command -v rsync >/dev/null || { echo "ERROR: rsync not found. Install it (or run from WSL / Linux / macOS)."; exit 1; }

PI_HOST="michael@homecam"
REMOTE_DIR="/home/michael/homecam"

echo "==> Syncing files to Pi..."
rsync -avz --exclude='.git/' \
           --exclude='snapshots/' \
           --exclude='backup/' \
           --exclude='nginx/certs/' \
           --exclude='nginx/htpasswd' \
           --exclude='.env' \
           --exclude='__pycache__/' \
           --exclude='*.pyc' \
    . "${PI_HOST}:${REMOTE_DIR}/"

echo ""
echo "==> Creating local directories on Pi if missing..."
ssh "${PI_HOST}" "mkdir -p ${REMOTE_DIR}/snapshots ${REMOTE_DIR}/backup ${REMOTE_DIR}/nginx/certs"

echo ""
echo "==> Checking .env exists on Pi..."
ssh "${PI_HOST}" "test -f ${REMOTE_DIR}/.env || { echo 'ERROR: .env not found on Pi. Copy .env.example and fill in values.'; exit 1; }"

echo ""
echo "==> Checking nginx/htpasswd exists on Pi..."
ssh "${PI_HOST}" "test -f ${REMOTE_DIR}/nginx/htpasswd || { echo 'ERROR: nginx/htpasswd not found. Run: htpasswd -nb michael <password> > nginx/htpasswd'; exit 1; }"

echo ""
echo "==> Building images and starting containers..."
ssh "${PI_HOST}" "cd ${REMOTE_DIR} && docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"

echo ""
echo "==> Tailing app logs (Ctrl-C to stop)..."
ssh "${PI_HOST}" "cd ${REMOTE_DIR} && docker compose logs --tail=30 -f app"
