#!/usr/bin/env bash
set -euo pipefail

if [ ! -d ".venv" ]; then
  python -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

echo "Starting FastAPI on http://0.0.0.0:8000 ..."
uvicorn server.feishu_callback:app --host 0.0.0.0 --port 8000 --reload
