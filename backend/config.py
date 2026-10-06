import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
MAX_BYTES = 200 * 1024 * 1024
MAX_DURATION = 300


class Settings:
    def __init__(self, data_dir=None):
        load_dotenv(ROOT / '.env')
        self.data_dir = Path(data_dir or os.getenv('DATA_DIR', 'data'))
        if not self.data_dir.is_absolute():
            self.data_dir = ROOT / self.data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = os.getenv('DASHSCOPE_API_KEY', '').strip()
        self.workspace = os.getenv('BAILIAN_WORKSPACE_ID', '').strip()
        self.asr_model = os.getenv('ASR_MODEL', 'fun-asr-realtime')
        self.vision_model = os.getenv('VISION_MODEL', 'qwen3.6-flash')
        host = f'{self.workspace}.cn-beijing.maas.aliyuncs.com'
        self.http_base = os.getenv('BAILIAN_HTTP_BASE_URL', '').strip() or f'https://{host}/compatible-mode/v1'
        self.ws_url = os.getenv('BAILIAN_WS_URL', '').strip() or f'wss://{host}/api-ws/v1/inference'

    @property
    def missing(self):
        fields = []
        if not self.api_key:
            fields.append('DASHSCOPE_API_KEY')
        if not self.workspace and not (os.getenv('BAILIAN_HTTP_BASE_URL') and os.getenv('BAILIAN_WS_URL')):
            fields.append('BAILIAN_WORKSPACE_ID')
        return fields

