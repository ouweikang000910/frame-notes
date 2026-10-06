"""Start the localhost-only application and open a browser when the server is ready."""
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import uvicorn
from dotenv import load_dotenv

load_dotenv(ROOT / '.env')
port = int(os.getenv('PORT', '8765'))
url = f'http://127.0.0.1:{port}'
with socket.socket() as probe:
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind(('127.0.0.1', port))
    except OSError:
        print(f'端口 {port} 已被使用。若拆片已经启动，请打开 {url}；否则修改 .env 中的 PORT。')
        sys.exit(1)


def open_when_ready():
    for _ in range(100):
        try:
            with socket.create_connection(('127.0.0.1', port), timeout=0.2):
                webbrowser.open(url)
                return
        except OSError:
            time.sleep(0.2)


if os.getenv('NO_BROWSER') != '1':
    threading.Thread(target=open_when_ready, daemon=True).start()
print(f'拆片已启动：{url}\n关闭服务：在此终端按 Ctrl+C。')
uvicorn.run('backend.main:create_app', factory=True, host='127.0.0.1', port=port)
