#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -d frontend/node_modules ]; then bash scripts/setup.sh; fi
if [ ! -f .env ]; then cp .env.example .env; fi
(cd frontend && npm run build)
exec .venv/bin/python scripts/serve.py

