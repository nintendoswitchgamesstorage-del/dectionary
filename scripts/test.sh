#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
.venv/bin/python -m pytest backend desktop -q
npm run build
if [[ "${1:-}" == "--browser" ]]; then
  LEXICAL_TEST_PYTHON="$PWD/.venv/bin/python" npm run test:e2e
fi
