#!/usr/bin/env bash
set -euo pipefail

if ! command -v ngrok >/dev/null 2>&1; then
  echo "ngrok not found. Install with: brew install ngrok/ngrok/ngrok"
  exit 1
fi

echo "Starting ngrok on port 8000 ..."
ngrok http 8000
