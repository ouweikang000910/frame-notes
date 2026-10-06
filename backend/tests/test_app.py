import copy
import io
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.ai import Bailian, service_error
from backend.config import MAX_BYTES, Settings
from backend.main import create_app
from backend.media import AnalysisError, canonical_url, extract_url, prepare_video, probe, run_ffmpeg
from backend.pipeline import validate_shots
from backend.storage import Store


class FakeAI:
    """Controlled service adapter; media processing and HTTP API remain real."""
    def __init__(self, fail_summary=False):
        self.transcriptions = self.chunks = self.summaries = 0
        self.fail_summary = fail_summary

    def transcribe(self, audio):
        assert audio.is_file()
        self.transcriptions += 1
        return [{'id': 't-0', 'start': 0, 'end': 1.5, 'text': '先提出问题。'},
                {'id': 't-1', 'start': 1.5, 'end': 3.0, 'text': '再展示解决方法。'}]

    def analyze_chunk(self, folder, start, end, frames, transcript, scenes):
        assert frames and all((folder / f['file']).is_file() for f in frames)
        self.chunks += 1
        split = (start + end) / 2
        return {'shots': [{'start': start, 'end': split, 'description': '红色画面', 'role': '提出问题', 'rhythm': '短句开场', 'uncertain': False},
                          {'start': split, 'end': end, 'description': '蓝色画面', 'role': '给出方法', 'rhythm': '切镜推进', 'uncertain': False}], 'notes': '问题→方法'}

    def summarize(self, transcript, chunks):
        self.summaries += 1
        if self.fail_summary and self.summaries == 1:
            raise AnalysisError('ai_quota', '百炼额度不足，请检查账户后重试。')
        return dict(topic='创作方法', audience='内容创作者（推断）', hook='先提出问题', structure='0–1.5秒问题，1.5–3秒方法',
                    rhythm='切镜推进', observations='画面在中段变化', takeaways='可以借鉴问题→方法结构', uncertainties='无')


@pytest.fixture(scope='session')
def videos(tmp_path_factory):
    folder = tmp_path_factory.mktemp('videos')
    silent = folder / 'silent.mp4'
    audio = folder / 'audio.mp4'
    run_ffmpeg(['-f', 'lavfi', '-i', 'color=c=red:s=64x96:r=6:d=1.5', '-f', 'lavfi', '-i', 'color=c=blue:s=64x96:r=6:d=1.5',
                '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(silent)])
    run_ffmpeg(['-i', str(silent), '-f', 'lavfi', '-i', 'sine=frequency=440:duration=3', '-c:v', 'copy', '-c:a', 'aac', '-shortest', str(audio)])
    return folder, silent, audio


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
    monkeypatch.delenv('BAILIAN_WORKSPACE_ID', raising=False)
    result = Settings(tmp_path / 'data')
    result.api_key = ''; result.workspace = ''
    return result


def wait_for(client, identifier, expected):
    for _ in range(200):
        result = client.get('/api/analyses/' + identifier).json()
        if result['status'] == expected:
            return result
        if result['status'] == 'failed' and expected != 'failed':
            pytest.fail(str(result['error']))
        time.sleep(0.05)
    pytest.fail('Pipeline did not complete in time')


@pytest.mark.parametrize('text,expected', [
    ('https://www.douyin.com/video/123456789', 'https://www.douyin.com/video/123456789'),
    ('2.34 复制打开抖音，看看作品！ https://v.douyin.com/AbC123/ 复制此链接', 'https://v.douyin.com/AbC123/'),
    ('看这个：https://v.douyin.com/AbC123/。', 'https://v.douyin.com/AbC123/'),
    ('https://www.douyin.com/?modal_id=123456789', 'https://www.douyin.com/?modal_id=123456789'),
])
def test_link_extraction(text, expected):
    assert extract_url(text) == expected


@pytest.mark.parametrize('text', ['hello', 'https://evil.com/', 'http://127.0.0.1/video/1', 'https://douyin.com.evil.com/video/1', 'https://douyin.com:8443/video/1'])
def test_bad_links(text):
    with pytest.raises(AnalysisError): extract_url(text)


def test_short_link_redirect(monkeypatch):
    original = httpx.Client
    def handler(request):
        return httpx.Response(302, headers={'location': 'https://www.iesdouyin.com/share/video/123456789/?abc=1'})
    monkeypatch.setattr('backend.media.httpx.Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    assert canonical_url('https://v.douyin.com/AbC/') == 'https://www.douyin.com/video/123456789'


def test_redirect_does_not_fetch_other_hosts(monkeypatch):
    original = httpx.Client
    calls = []
    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(302, headers={'location': 'http://127.0.0.1/private'})
    monkeypatch.setattr('backend.media.httpx.Client', lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs))
    with pytest.raises(AnalysisError): canonical_url('https://v.douyin.com/AbC/')
    assert len(calls) == 1


def test_real_media(videos, tmp_path):
    _, silent, _ = videos
    metadata, frames, scenes = prepare_video(silent, tmp_path)
    assert metadata['duration'] == 3
    assert metadata['has_audio'] is False
    assert (tmp_path / 'video.mp4').is_file() and (tmp_path / 'cover.jpg').is_file()
    assert frames[0]['time'] == 0
    assert any(abs(value - 1.5) < 0.2 for value in scenes)
    assert all(0 <= f['time'] < 3 for f in frames)


def test_media_limits(videos, tmp_path):
    corrupted = tmp_path / 'bad.mp4'; corrupted.write_bytes(b'not a video')
    with pytest.raises(AnalysisError, match='损坏'): probe(corrupted)
    large = tmp_path / 'large.mp4'
    with large.open('wb') as target: target.truncate(MAX_BYTES + 1)
    with pytest.raises(AnalysisError, match='200MB'): probe(large)
    long = tmp_path / 'long.mp4'
    run_ffmpeg(['-f', 'lavfi', '-i', 'color=s=16x16:r=1:d=301', '-c:v', 'libx264', str(long)])
    with pytest.raises(AnalysisError, match='5分钟'): probe(long)


def test_full_upload_edit_export_persistence(settings, videos):
    _, _, audio = videos
    fake = FakeAI()
    app = create_app(settings, fake)
    with TestClient(app) as client:
        response = client.post('/api/analyses/upload', files={'file': ('参考.mp4', audio.read_bytes(), 'video/mp4')})
        assert response.status_code == 202
        identifier = response.json()['id']
        doc = wait_for(client, identifier, 'completed')
        assert fake.transcriptions == 1 and len(doc['shots']) == 2 and len(doc['transcript']) == 2
        assert '_cache' not in doc
        playback = client.get(doc['video_url'], headers={'Range': 'bytes=0-63'})
        assert playback.status_code == 206 and len(playback.content) == 64
        assert client.get(doc['shots'][0]['thumbnail']).status_code == 200
        body = {key: copy.deepcopy(doc[key]) for key in ('title', 'overview', 'transcript', 'shots')}
        body['title'] = '我的创作参考'; body['overview']['hook'] = '保存后的钩子'
        body['shots'][0]['description'] = '=测试导出安全'
        body['transcript'][0]['text'] = '修改后的文案'
        assert client.patch('/api/analyses/' + identifier, json=body).status_code == 200
        markdown = client.get(f'/api/analyses/{identifier}/export?format=markdown')
        csv = client.get(f'/api/analyses/{identifier}/export?format=csv')
        assert '保存后的钩子' in markdown.text and '修改后的文案' in markdown.text
        assert csv.content.startswith(b'\xef\xbb\xbf')
        assert "'=测试导出安全" in csv.content.decode('utf-8-sig')
        bad = copy.deepcopy(body); bad['shots'][0]['end'] = 20
        assert client.patch('/api/analyses/' + identifier, json=bad).status_code == 422
        bad = copy.deepcopy(body); bad['shots'][1]['start'] = 0
        assert client.patch('/api/analyses/' + identifier, json=bad).status_code == 422
        assert client.get(f'/api/analyses/{identifier}/media/audio.wav').status_code == 404
        assert client.get(f'/api/analyses/{identifier}/export?format=html').status_code == 422
    reopened = create_app(settings, fake)
    with TestClient(reopened) as client:
        assert client.get('/api/analyses/' + identifier).json()['title'] == '我的创作参考'
        assert len(client.get('/api/analyses').json()) == 1
        assert client.delete('/api/analyses/' + identifier).status_code == 204
        assert not (settings.data_dir / identifier).exists()
        assert client.get('/api/analyses/' + identifier).status_code == 404


def test_retry_reuses_completed_stages(settings, videos):
    fake = FakeAI(fail_summary=True)
    app = create_app(settings, fake)
    with TestClient(app) as client:
        response = client.post('/api/analyses/upload', files={'file': ('test.mp4', videos[2].read_bytes(), 'video/mp4')})
        identifier = response.json()['id']
        failed = wait_for(client, identifier, 'failed')
        assert failed['error']['code'] == 'ai_quota'
        assert client.post('/api/analyses/' + identifier + '/retry').status_code == 202
        wait_for(client, identifier, 'completed')
        assert fake.transcriptions == 1 and fake.chunks == 1 and fake.summaries == 2


def test_silent_video(settings, videos):
    fake = FakeAI()
    with TestClient(create_app(settings, fake)) as client:
        response = client.post('/api/analyses/upload', files={'file': ('silent.mp4', videos[1].read_bytes())})
        doc = wait_for(client, response.json()['id'], 'completed')
        assert doc['transcript'] == [] and doc['warnings'] and doc['shots']
        assert fake.transcriptions == 0


def test_not_configured_and_bad_upload(settings, videos):
    app = create_app(settings)
    with TestClient(app) as client:
        health = client.get('/api/health').json()
        assert health['configured'] is False and health['media_available']
        response = client.post('/api/analyses/upload', files={'file': ('bad.mp4', b'broken')})
        assert response.status_code == 400 and response.json()['code'] == 'invalid_video'
        assert client.get('/api/analyses').json() == []
        assert client.post('/api/analyses/upload', files={'file': ('audio.mp3', b'broken')}).status_code == 400
        response = client.post('/api/analyses/upload', files={'file': ('test.mp4', videos[2].read_bytes())})
        doc = wait_for(client, response.json()['id'], 'failed')
        assert doc['error']['code'] == 'not_configured' and doc['video_url']
        assert client.get(doc['video_url']).status_code == 200
        assert client.get('/api/health').json()['missing'] == ['DASHSCOPE_API_KEY', 'BAILIAN_WORKSPACE_ID']


def test_download_failure_then_upload(settings, videos, monkeypatch):
    def blocked(*args): raise AnalysisError('download_failed', '抖音要求 Cookie，请上传视频')
    monkeypatch.setattr('backend.pipeline.download_video', blocked)
    with TestClient(create_app(settings, FakeAI())) as client:
        result = client.post('/api/analyses', json={'text': '分享 https://v.douyin.com/abc/'}).json()
        identifier = result['id']
        wait_for(client, identifier, 'failed')
        response = client.post(f'/api/analyses/{identifier}/upload', files={'file': ('replacement.mp4', videos[1].read_bytes())})
        assert response.status_code == 202
        result = wait_for(client, identifier, 'completed')
        assert result['source_type'] == 'upload' and result['source_url']
        assert len(client.get('/api/analyses').json()) == 1


def test_local_origin_and_invalid_input(settings):
    with TestClient(create_app(settings)) as client:
        assert client.post('/api/analyses', json={'text': 'https://example.com'}).status_code == 400
        assert client.post('/api/analyses', json={'text': ''}).status_code == 422
        assert client.post('/api/analyses', headers={'Origin': 'https://evil.com'}, json={'text': 'x'}).status_code == 403
        assert client.get('/api/health', headers={'Host': 'evil.com'}).status_code == 400


def test_recovery_after_restart(settings):
    store = Store(settings.data_dir / 'analyses.sqlite3')
    doc = store.create('中断任务')
    with TestClient(create_app(settings)) as client:
        recovered = client.get('/api/analyses/' + doc['id']).json()
        assert recovered['status'] == 'failed' and recovered['error']['code'] == 'interrupted'


def test_single_active_task(settings, monkeypatch):
    import threading
    gate = threading.Event()
    def blocked(*args):
        gate.wait(3)
        raise AnalysisError('download_failed', '测试阻挡')
    monkeypatch.setattr('backend.pipeline.download_video', blocked)
    with TestClient(create_app(settings)) as client:
        first = client.post('/api/analyses', json={'text': 'https://www.douyin.com/video/123456789'})
        assert first.status_code == 202
        assert client.post('/api/analyses', json={'text': 'https://www.douyin.com/video/123456789'}).status_code == 409
        assert client.delete('/api/analyses/' + first.json()['id']).status_code == 409
        gate.set()
        wait_for(client, first.json()['id'], 'failed')


@pytest.mark.parametrize('status,code,expected', [(401, '', 'ai_auth'), (400, 'QuotaExceeded', 'ai_quota'), (429, '', 'ai_rate_limit'), (404, '', 'ai_model')])
def test_ai_errors(status, code, expected):
    assert service_error(status, code).code == expected


def test_http_timeout(settings, monkeypatch):
    settings.api_key = 'test-not-a-real-key'; settings.workspace = 'test'
    original = httpx.Client
    def timeout(request): raise httpx.ReadTimeout('timeout')
    monkeypatch.setattr('backend.ai.httpx.Client', lambda **kwargs: original(transport=httpx.MockTransport(timeout), **kwargs))
    with pytest.raises(AnalysisError) as result: Bailian(settings).request([{'type': 'text', 'text': 'test'}])
    assert result.value.code == 'ai_timeout'


def test_invalid_shot_ranges():
    with pytest.raises(AnalysisError):
        validate_shots([{'start': 0, 'end': 40, 'description': 'x', 'role': 'x', 'rhythm': 'x'}], 0, 30, [], [], 0)

