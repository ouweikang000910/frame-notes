#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v node >/dev/null || ! command -v npm >/dev/null; then
  echo '请先安装 Node.js 22 或更高版本：https://nodejs.org/'
  exit 1
fi
if ! node -e 'const [major,minor]=process.versions.node.split(".").map(Number);process.exit(major>=24 || (major===22 && minor>=12) ? 0 : 1)' ; then
  echo '需要 Node.js 22.12+ 或24+，请更新 Node.js 后再次运行。'
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  TASK_PYTHON=''
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 "$HOME/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3"; do
    if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
      TASK_PYTHON="$candidate"
      break
    fi
  done
  if [ -z "$TASK_PYTHON" ]; then
    echo '请先安装 Python 3.10 或更高版本：https://www.python.org/downloads/'
    exit 1
  fi
  "$TASK_PYTHON" -m venv .venv
fi

echo '正在安装本地分析依赖（含 FFmpeg，无需额外安装）…'
TASK_REQUIREMENTS=backend/requirements.txt
if [ -f backend/requirements.lock.txt ]; then TASK_REQUIREMENTS=backend/requirements.lock.txt; fi
.venv/bin/python -m pip install -r "$TASK_REQUIREMENTS"
(cd frontend && npm ci --no-audit --no-fund && npm run build)
if [ ! -f .env ]; then cp .env.example .env; fi
mkdir -p data
echo '安装完成。填写 .env 中的百炼信息，然后双击“启动拆片.command”。'
