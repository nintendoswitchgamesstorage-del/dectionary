#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 -m venv .venv
.venv/bin/python -m pip install --cache-dir .data/package-cache/pip -r backend/requirements.lock
npm ci --cache .data/package-cache/npm --no-audit --no-fund
npm run build
.venv/bin/python -c 'from backend.storage import Library; Library().bootstrap()'
printf 'Lexical Alchemy is installed. Run bash scripts/dev.sh to start the laboratory.\n'
