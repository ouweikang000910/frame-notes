import json
import math
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import av
import httpx
import imageio_ffmpeg

from .config import MAX_BYTES, MAX_DURATION


class AnalysisError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


ALLOWED_HOSTS = {'douyin.com', 'www.douyin.com', 'v.douyin.com', 'iesdouyin.com', 'www.iesdouyin.com'}


def validate_douyin_url(url):
    parts = urlparse(url)
    if parts.scheme not in ('http', 'https') or parts.hostname not in ALLOWED_HOSTS or parts.username or parts.password or parts.port not in (None, 80, 443):
        raise AnalysisError('invalid_link', '请输入抖音视频链接，支持分享文本、v.douyin.com 短链接和视频详情链接。')
    return url


def extract_url(text):
    matches = re.findall(r'https?://[^\s<>"“”《》]+', text)
    for value in matches:
        value = value.rstrip('。；，！、,.;!）)]}')
        try:
            return validate_douyin_url(value)
        except (AnalysisError, ValueError):
            continue
    raise AnalysisError('invalid_link', '没有找到有效的抖音链接，请粘贴视频分享链接或完整分享文本。')


def canonical_url(url):
    validate_douyin_url(url)
    parts = urlparse(url)
    identifier = re.search(r'/(?:share/)?video/(\d+)', parts.path)
    identifier = identifier.group(1) if identifier else (parse_qs(parts.query).get('modal_id') or [None])[0]
    if identifier and identifier.isdigit():
        return f'https://www.douyin.com/video/{identifier}'
    if parts.hostname != 'v.douyin.com':
        raise AnalysisError('invalid_link', '当前支持单条抖音视频，请使用视频详情链接或分享短链接。')
    # Validate each redirect before following it; never fetch arbitrary user-provided hosts.
    try:
        with httpx.Client(timeout=15, headers={'User-Agent': 'Mozilla/5.0'}, trust_env=True) as client:
            for _ in range(5):
                response = client.get(url, follow_redirects=False)
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url = validate_douyin_url(urljoin(url, response.headers['location']))
                    parts = urlparse(url)
                    match = re.search(r'/(?:share/)?video/(\d+)', parts.path)
                    identifier = match.group(1) if match else (parse_qs(parts.query).get('modal_id') or [None])[0]
                    if identifier and identifier.isdigit():
                        return f'https://www.douyin.com/video/{identifier}'
                else:
                    break
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise AnalysisError('download_failed', '抖音短链接暂时无法访问，请稍后重试，或上传已保存的视频继续分析。') from exc
    raise AnalysisError('download_failed', '短链接未解析到单条视频，请重新复制链接，或上传视频继续分析。')


def download_video(url, folder):
    canonical = canonical_url(url)
    args = [sys.executable, '-m', 'yt_dlp', '--ignore-config', '--no-playlist', '--no-progress',
            '--socket-timeout', '15', '--retries', '1', '--extractor-retries', '1',
            '--max-filesize', '200M', '--match-filter', 'duration <= 300',
            '-f', 'best[ext=mp4]/best', '--dump-single-json',
            '-o', str(folder / 'source.%(ext)s'), canonical]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=150)
    except subprocess.TimeoutExpired as exc:
        raise AnalysisError('download_failed', '抖音视频获取超时，请重试或上传已保存的视频。') from exc
    if result.returncode:
        stderr = result.stderr.lower()
        if 'cookie' in stderr:
            message = '抖音要求更新访问 Cookie，当前无法直接获取。请上传已保存的视频继续分析。'
        elif 'private' in stderr or 'not available' in stderr:
            message = '视频不可访问，可能已删除或不是公开视频。请换一个链接或上传视频。'
        else:
            message = '抖音限制了此次获取，或视频链接已失效。可以重试，或上传视频继续分析。'
        raise AnalysisError('download_failed', message)
    try:
        info = json.loads(result.stdout)
    except json.JSONDecodeError:
        info = {}
    sources = [p for p in folder.glob('source.*') if p.suffix.lower() in ('.mp4', '.mov', '.webm', '.mkv')]
    if not sources:
        if (info.get('duration') or 0) > MAX_DURATION:
            raise AnalysisError('too_long', '第一版支持5分钟以内的视频，请截取片段后上传。')
        if (info.get('filesize') or info.get('filesize_approx') or 0) > MAX_BYTES:
            raise AnalysisError('too_large', '视频超过200MB，请压缩后上传。')
        raise AnalysisError('download_failed', '未获取到可分析的视频文件，请上传视频继续分析。')
    return sources[0], info.get('title') or '抖音视频', canonical


def ffmpeg():
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:
        raise AnalysisError('missing_ffmpeg', '未找到 FFmpeg，请重新运行安装脚本安装视频处理依赖。') from exc


def run_ffmpeg(args, timeout=180):
    try:
        result = subprocess.run([ffmpeg(), '-hide_banner', '-nostdin', '-y', *args],
                                capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        raise AnalysisError('processing_timeout', '视频处理超时，请压缩视频后重试。') from exc
    if result.returncode:
        raise AnalysisError('invalid_video', '无法解码视频，请上传有效的 MP4 或 MOV 文件。')
    return result


def probe(path):
    if path.stat().st_size > MAX_BYTES:
        raise AnalysisError('too_large', '视频超过200MB，请压缩后重新上传。')
    try:
        with av.open(str(path)) as container:
            if not container.streams.video:
                raise ValueError('No video track')
            stream = container.streams.video[0]
            duration = (container.duration / av.time_base if container.duration else
                        float(stream.duration * stream.time_base) if stream.duration else 0)
            if not math.isfinite(duration) or duration <= 0:
                raise ValueError('Invalid duration')
            if duration > MAX_DURATION + 0.05:
                raise AnalysisError('too_long', '视频超过5分钟，请截取需要拆解的片段后上传。')
            return dict(duration=round(duration, 3), width=stream.width, height=stream.height,
                        has_audio=bool(container.streams.audio))
    except AnalysisError:
        raise
    except Exception as exc:
        raise AnalysisError('invalid_video', '文件不是有效的视频，或文件已经损坏，请重新上传 MP4 / MOV。') from exc


def prepare_video(source, folder):
    metadata = probe(source)
    # A replacement source must not reuse frames left by a previous failed attempt.
    for pattern in ('frame-*.jpg', 'scene-*.jpg', 'video.mp4', 'audio.wav', 'cover.jpg'):
        for previous in folder.glob(pattern):
            previous.unlink(missing_ok=True)
    video = folder / 'video.mp4'
    run_ffmpeg(['-i', str(source), '-map', '0:v:0', '-map', '0:a:0?',
                '-vf', 'scale=960:960:force_original_aspect_ratio=decrease:force_divisible_by=2',
                '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23', '-pix_fmt', 'yuv420p',
                '-c:a', 'aac', '-movflags', '+faststart', str(video)])
    if metadata['has_audio']:
        run_ffmpeg(['-i', str(video), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(folder / 'audio.wav')])
    result = run_ffmpeg(['-i', str(video), '-an', '-vf', "scale=160:-2,select='gt(scene,0.30)',showinfo", '-f', 'null', '-'])
    scenes = sorted({round(float(t), 3) for t in re.findall(r'pts_time:([\d.]+)', result.stderr)
                     if float(t) < metadata['duration']})
    # Uniform frames preserve actual PTS from showinfo. Scene frames add evidence between them.
    result = run_ffmpeg(['-i', str(video), '-an', '-vf', 'fps=1,scale=640:640:force_original_aspect_ratio=decrease,showinfo',
                        '-q:v', '4', str(folder / 'frame-%04d.jpg')])
    actual_times = [float(t) for t in re.findall(r'pts_time:([\d.]+)', result.stderr)]
    frames = []
    for index, path in enumerate(sorted(folder.glob('frame-*.jpg'))):
        time = actual_times[index] if index < len(actual_times) else float(index)
        if time < metadata['duration']:
            frames.append({'time': time, 'file': path.name})
    # Very short videos can have no output at 1 FPS.
    if not frames:
        snapshot(video, folder / 'frame-0001.jpg', 0)
        frames = [{'time': 0.0, 'file': 'frame-0001.jpg'}]
    for index, time in enumerate(scenes):
        if all(abs(time - frame['time']) > 0.2 for frame in frames):
            name = f'scene-{index:04d}.jpg'
            snapshot(video, folder / name, time)
            frames.append({'time': time, 'file': name})
    frames.sort(key=lambda f: f['time'])
    snapshot(video, folder / 'cover.jpg', min(0.1, metadata['duration'] / 2))
    return metadata, frames, scenes


def snapshot(video, output, time):
    run_ffmpeg(['-ss', str(time), '-i', str(video), '-frames:v', '1',
                '-vf', 'scale=640:640:force_original_aspect_ratio=decrease', '-q:v', '4', str(output)], timeout=30)
