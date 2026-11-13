#!/usr/bin/env bash
set -e

# Ensure KEK master key exists if needed for blob decryption
KEK_PATH="${KEK_PATH:-/run/secrets/kek.json}"
if [ ! -f "$KEK_PATH" ]; then
    if [ ! -f "/app/secrets/kek.json" ]; then
        echo "[INFO] Master key (KEK) not found. Generating new key in /app/secrets/kek.json..."
        mkdir -p /app/secrets
        python -m dbresearch.cli kek-init --out /app/secrets/kek.json 2>/dev/null || true
    fi
fi

# Execute command (default: python -m dbresearch.worker)
if [ $# -gt 0 ]; then
    echo "[INFO] Executing command: $*"
    exec "$@"
else
    echo "[INFO] Starting OCR Worker..."
    exec python -m dbresearch.worker
fi
