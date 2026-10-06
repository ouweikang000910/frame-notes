import math
import threading
from concurrent.futures import ThreadPoolExecutor

from .ai import Bailian
from .media import AnalysisError, download_video, prepare_video
from .models import Overview


class Pipeline:
    def __init__(self, settings, store, ai=None):
        self.settings, self.store = settings, store
        self.ai = ai or Bailian(settings)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='analysis')
        self.lock = threading.Lock()
        self.active_id = None

    def submit(self, identifier):
        with self.lock:
            if self.active_id:
                raise AnalysisError('busy', '已有视频正在分析，请等待当前任务完成后再提交。')
            self.active_id = identifier
            self.store.update(identifier, status='queued', error=None, message='任务已提交，正在准备')
            self.executor.submit(self.run, identifier)

    def progress(self, identifier, stage, value, message, **fields):
        self.store.update(identifier, status='running', stage=stage, progress=value, message=message, **fields)

    def run(self, identifier):
        folder = self.settings.data_dir / identifier
        folder.mkdir(parents=True, exist_ok=True)
        try:
            doc = self.store.get(identifier)
            cache = doc['_cache']
            if not cache.get('source'):
                self.progress(identifier, 'acquiring', 5, '正在解析抖音链接并获取视频')
                source, title, url = download_video(doc['source_url'], folder)
                cache['source'] = source.name
                self.store.update(identifier, title=title[:200], source_url=url, _cache=cache)
            if not cache.get('prepared'):
                self.progress(identifier, 'preparing', 15, '正在提取音频、检测镜头变化和抽取画面')
                metadata, frames, scenes = prepare_video(folder / cache['source'], folder)
                cache.update(prepared=True, frames=frames, scenes=scenes, has_audio=metadata.pop('has_audio'))
                self.store.update(identifier, **metadata, _cache=cache)
            doc = self.store.get(identifier)
            duration = doc['duration']
            if not cache.get('transcribed'):
                self.progress(identifier, 'transcribing', 30, '正在识别语音，生成带时间戳的文案')
                sentences = self.ai.transcribe(folder / 'audio.wav') if cache['has_audio'] else []
                for item in sentences:
                    if not (0 <= item['start'] < item['end'] <= duration + 0.5):
                        raise AnalysisError('ai_format', '语音时间戳超出视频范围，请重试语音识别阶段。')
                    item['end'] = min(item['end'], duration)
                cache['transcribed'] = True
                warning = [] if sentences else ['未识别到语音，文案为空；画面分析仍会继续。']
                self.store.update(identifier, transcript=sentences, warnings=warning, _cache=cache)
            doc = self.store.get(identifier)
            transcript = doc['transcript']
            chunks = cache.setdefault('chunks', [])
            count = math.ceil(duration / 30)
            for index in range(len(chunks), count):
                start, end = index * 30, min((index + 1) * 30, duration)
                self.progress(identifier, 'analyzing', 40 + int(index / count * 40), f'正在拆解画面与结构 · {index + 1}/{count} 段')
                frames = [f for f in cache['frames'] if start <= f['time'] < end]
                if not frames:
                    frames = [min(cache['frames'], key=lambda f: abs(f['time'] - start))]
                # At most 60 evidence frames per call; preserve temporal coverage on dense cuts.
                if len(frames) > 60:
                    frames = [frames[round(i * (len(frames) - 1) / 59)] for i in range(60)]
                sentences = [s for s in transcript if s['end'] > start and s['start'] < end]
                scenes = [t for t in cache['scenes'] if start <= t < end]
                result = self.ai.analyze_chunk(folder, start, end, frames, sentences, scenes)
                result['shots'] = validate_shots(result.get('shots'), start, end, frames, sentences, index)
                chunks.append(result)
                self.store.update(identifier, shots=[shot for chunk in chunks for shot in chunk['shots']], _cache=cache)
            self.progress(identifier, 'summarizing', 90, '正在汇总开头钩子、内容结构和创作方法')
            overview = Overview.model_validate(self.ai.summarize(transcript, chunks)).model_dump()
            # All eight fields are required for a meaningful summary, including explicit uncertainties.
            if any(not value.strip() for value in overview.values()):
                raise AnalysisError('ai_format', '整体分析存在空字段，请重试汇总阶段。')
            cache['summarized'] = True
            self.store.update(identifier, overview=overview, _cache=cache, status='completed', stage='completed',
                              progress=100, message='拆解完成，可以对照视频修改和导出', error=None)
        except AnalysisError as exc:
            self.store.update(identifier, status='failed', message=exc.message, error={'code': exc.code, 'message': exc.message})
        except Exception:
            self.store.update(identifier, status='failed', message='此阶段未完成，已保留缓存，请重试。',
                              error={'code': 'processing_error', 'message': '处理结果异常，请重试当前阶段；若持续出现，请检查依赖与模型配置。'})
        finally:
            with self.lock:
                self.active_id = None


def validate_shots(items, start, end, frames, transcript, chunk_index):
    if not isinstance(items, list) or not items:
        raise AnalysisError('ai_format', 'AI未返回有效分镜，请重试当前片段。')
    shots = []
    for index, item in enumerate(items):
        try:
            begin, finish = float(item['start']), float(item['end'])
            if not (math.isfinite(begin) and math.isfinite(finish) and start <= begin < finish <= end):
                raise ValueError('Invalid range')
            if shots and begin < shots[-1]['end']:
                raise ValueError('Overlapping shots')
            description, role, rhythm = (item[key] for key in ('description', 'role', 'rhythm'))
            if not all(isinstance(value, str) and value.strip() for value in (description, role, rhythm)):
                raise ValueError('Empty observation')
            shot_frames = [frame for frame in frames if begin <= frame['time'] < finish]
            thumbnail = min(shot_frames or frames, key=lambda f: abs(f['time'] - (begin + finish) / 2))['file']
            shots.append(dict(id=f's-{chunk_index}-{index}', start=begin, end=finish,
                              text=''.join(s['text'] for s in transcript if s['end'] > begin and s['start'] < finish),
                              description=description, role=role, rhythm=rhythm, thumbnail=thumbnail,
                              uncertain=bool(item.get('uncertain', False))))
        except (KeyError, TypeError, ValueError) as exc:
            raise AnalysisError('ai_format', '分镜时间或内容格式不正确，请重试当前片段。') from exc
    return shots

