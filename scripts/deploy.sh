#!/usr/bin/env bash
set -Eeuo pipefail

APP_DIR="${APP_DIR:-/home/sargon_erp}"
SOURCE_DIR="${SOURCE_DIR:-${GITHUB_WORKSPACE:-$(pwd)}}"
LOCK_FILE="${LOCK_FILE:-/tmp/sargon_erp_deploy.lock}"
PYTHON_BIN="${PYTHON_BIN:-python3}"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another deploy is already running."
  exit 1
fi

if [ ! -f "$SOURCE_DIR/requirements.txt" ] || [ ! -f "$SOURCE_DIR/frontend/package.json" ] || [ ! -f "$SOURCE_DIR/sargon_erp/manage.py" ]; then
  echo "Invalid source directory: $SOURCE_DIR"
  exit 1
fi

if [ ! -f "$APP_DIR/.env" ]; then
  echo "Missing production environment file: $APP_DIR/.env"
  exit 1
fi

mkdir -p "$APP_DIR"

rsync -az --delete \
  --exclude ".git/" \
  --exclude ".github/" \
  --exclude ".env" \
  --exclude "venv/" \
  --exclude "frontend/node_modules/" \
  --exclude "frontend/dist/" \
  --exclude "sargon_erp/media/" \
  --exclude "**/__pycache__/" \
  --exclude "*.pyc" \
  "$SOURCE_DIR"/ "$APP_DIR"/

cd "$APP_DIR"

if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$APP_DIR/venv"
fi

"$APP_DIR/venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

cd "$APP_DIR/frontend"
if [ -f package-lock.json ]; then
  npm ci
else
  npm install
fi
npm run build

cd "$APP_DIR"
"$APP_DIR/venv/bin/python" sargon_erp/manage.py migrate --noinput
"$APP_DIR/venv/bin/python" sargon_erp/manage.py collectstatic --noinput
"$APP_DIR/venv/bin/python" sargon_erp/manage.py check

systemctl restart sargon_erp.service
nginx -t
systemctl reload nginx

systemctl is-active --quiet sargon_erp.service
systemctl is-active --quiet nginx

echo "Deploy completed successfully."
