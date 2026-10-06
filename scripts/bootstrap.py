"""Portable dependency installation and local startup (Python 3.10+)."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = ROOT / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')


def run(command: list[str], cwd: Path = ROOT) -> None:
    # Let subprocess quote the npm batch wrapper for cmd.exe on Windows.
    batch = os.name == 'nt' and command[0].lower().endswith(('.cmd', '.bat'))
    subprocess.run(command, cwd=cwd, check=True, shell=batch)


def node_tools() -> tuple[str, str]:
    node, npm = shutil.which('node'), shutil.which('npm')
    if not node or not npm:
        raise RuntimeError('Install Node.js 24 LTS first: https://nodejs.org/')
    version = subprocess.check_output([node, '-p', 'process.versions.node'], text=True).strip()
    major, minor, *_ = (int(part) for part in version.split('.'))
    if not (major >= 24 or (major == 22 and minor >= 12)):
        raise RuntimeError('Node.js 22.12+ or 24+ is required. Recommended: Node.js 24 LTS.')
    return node, npm


def init_config() -> None:
    if not (ROOT / '.env').exists():
        shutil.copyfile(ROOT / '.env.example', ROOT / '.env')
    (ROOT / 'data').mkdir(exist_ok=True)


def install(npm: str) -> None:
    if sys.version_info < (3, 10):
        raise RuntimeError('Python 3.10+ is required. Recommended: Python 3.12.')
    if not VENV_PYTHON.is_file():
        run([sys.executable, '-m', 'venv', str(ROOT / '.venv')])
    print('Installing Python dependencies (including FFmpeg)...', flush=True)
    lock = ROOT / 'backend/requirements.lock.txt'
    requirements = lock if lock.is_file() else ROOT / 'backend/requirements.txt'
    run([str(VENV_PYTHON), '-m', 'pip', 'install', '-r', str(requirements)])
    run([npm, 'ci', '--no-audit', '--no-fund'], ROOT / 'frontend')
    run([npm, 'run', 'build'], ROOT / 'frontend')
    init_config()
    print('Ready. Set DASHSCOPE_API_KEY and BAILIAN_WORKSPACE_ID in .env, then start the app.')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'start'])
    args = parser.parse_args()
    try:
        _, npm = node_tools()
        if args.action == 'install':
            install(npm)
        else:
            if not VENV_PYTHON.is_file() or not (ROOT / 'frontend/node_modules').is_dir():
                install(npm)
            else:
                run([npm, 'run', 'build'], ROOT / 'frontend')
                init_config()
            run([str(VENV_PYTHON), str(ROOT / 'scripts/serve.py')])
    except KeyboardInterrupt:
        return 0
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(f'Unable to {args.action}: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
