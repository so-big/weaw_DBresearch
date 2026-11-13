#!/usr/bin/env bash
set -e

# Default port
PORT="${PORT:-8120}"
ROOT_ARG=""
CUSTOM_COMMAND=()

# Parse CLI arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --root)
      ROOT_ARG="$2"
      shift 2
      ;;
    --port)
      PORT="$2"
      shift 2
      ;;
    *)
      CUSTOM_COMMAND+=("$1")
      shift
      ;;
  esac
done

export PORT

# 1. Standalone PostgreSQL check (if DATABASE_URL is not set)
if [ -z "$DATABASE_URL" ]; then
    echo "[INFO] No DATABASE_URL provided. Starting internal PostgreSQL..."
    # Ensure postgres directory ownership
    if [ "$(id -u)" = "0" ]; then
        service postgresql start || true
        su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname = 'dbresearch'\" | grep -q 1 || psql -c \"CREATE USER dbresearch WITH PASSWORD 'dbresearch'; CREATE DATABASE dbresearch OWNER dbresearch;\"" || true
    fi
    export DATABASE_URL="postgresql+psycopg://dbresearch:dbresearch@localhost:5432/dbresearch"
fi

# 2. Ensure KEK master key exists
KEK_PATH="${KEK_PATH:-/run/secrets/kek.json}"
if [ ! -f "$KEK_PATH" ]; then
    if [ ! -f "/app/secrets/kek.json" ]; then
        echo "[INFO] Master key (KEK) not found. Generating new key in /app/secrets/kek.json..."
        mkdir -p /app/secrets
        python -m dbresearch.cli kek-init --out /app/secrets/kek.json || true
    fi
    if [ -f "/app/secrets/kek.json" ]; then
        KEK_PATH="/app/secrets/kek.json"
    fi
fi

# 3. Wait for PostgreSQL and run migrations
echo "[INFO] Waiting for database connection..."
python -c "
import os, time, sys
from sqlalchemy import create_engine, text
url = os.environ.get('DATABASE_URL')
for i in range(30):
    try:
        engine = create_engine(url, connect_args={'connect_timeout': 3})
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        sys.exit(0)
    except Exception:
        time.sleep(1)
sys.exit(0)
" || true

# Run migrations if this is not a worker container
if [ "${#CUSTOM_COMMAND[@]}" -eq 0 ] || [[ "${CUSTOM_COMMAND[*]}" != *"dbresearch.worker"* ]]; then
    echo "[INFO] Applying database migrations..."
    alembic upgrade head || true

    # 4. Provision / Update Admin User from root.txt, arguments, or environment variables
    SETUP_ARGS=()
    if [ -n "$ROOT_ARG" ]; then
        SETUP_ARGS+=("--root" "$ROOT_ARG")
    fi
    python -m dbresearch.setup_admin "${SETUP_ARGS[@]}" || true
fi

# If custom command was passed (e.g. worker), execute it
if [ "${#CUSTOM_COMMAND[@]}" -gt 0 ]; then
    echo "[INFO] Executing custom command: ${CUSTOM_COMMAND[*]}"
    exec "${CUSTOM_COMMAND[@]}"
fi

# 5. Print Web and API URLs banner
# Determine admin username for display
ADMIN_DISPLAY_USER="${ADMIN_USERNAME:-}"
if [ -z "$ADMIN_DISPLAY_USER" ]; then
    CRED_FILE="${ROOT_ARG:-${ROOT_FILE:-root.txt}}"
    if [ -f "$CRED_FILE" ]; then
        ADMIN_DISPLAY_USER=$(head -n 1 "$CRED_FILE" | tr -d '\r\n')
    fi
fi
ADMIN_DISPLAY_USER="${ADMIN_DISPLAY_USER:-admin}"

echo ""
echo "======================================================================"
echo "          DBresearch System Started Successfully!"
echo "======================================================================"
echo "  Web URL:      http://localhost:${PORT}"
echo "  API Docs URL: http://localhost:${PORT}/api/docs"
echo "  Admin User:   ${ADMIN_DISPLAY_USER}"
echo "  Port:         ${PORT}"
echo "======================================================================"
echo ""

# Start API web server
exec uvicorn dbresearch.main:app --host 0.0.0.0 --port "${PORT}"
