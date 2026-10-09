#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -x .venv/bin/python ]]; then
  printf 'Run bash scripts/setup.sh before starting Lexical Alchemy.\n' >&2
  exit 1
fi
.venv/bin/python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000 &
api_pid=$!
node node_modules/vite/bin/vite.js --host 0.0.0.0 --port 5173 --strictPort &
web_pid=$!
cleanup() {
  kill "$api_pid" "$web_pid" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
wait -n "$api_pid" "$web_pid"
