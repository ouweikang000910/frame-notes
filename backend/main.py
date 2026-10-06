import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote, urlparse

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from .config import MAX_BYTES, MAX_DURATION, ROOT, Settings
from .exports import markdown, storyboard_csv
from .media import AnalysisError, extract_url, ffmpeg, probe
from .models import EditInput, LinkInput
from .pipeline import Pipeline
from .storage import Store, public


def create_app(settings=None, ai=None):
    settings = settings or Settings()
    store = Store(settings.data_dir / 'analyses.sqlite3')
    pipeline = Pipeline(settings, store, ai)

    @asynccontextmanager
    async def lifespan(app):
        store.recover_interrupted()
        yield
        pipeline.executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title='拆片 · 本地视频拆解工具', lifespan=lifespan)
    app.state.store, app.state.pipeline, app.state.settings = store, pipeline, settings
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['localhost', '127.0.0.1', '[::1]', 'testserver'])

    @app.middleware('http')
    async def protect_local(request: Request, call_next):
        origin = request.headers.get('origin')
        if origin and urlparse(origin).hostname not in ('localhost', '127.0.0.1', '::1'):
            return JSONResponse({'detail': '工具仅接受本机网页请求。'}, status_code=403)
        return await call_next(request)

    @app.exception_handler(AnalysisError)
    async def analysis_error(request, exc):
        return JSONResponse({'detail': exc.message, 'code': exc.code}, status_code=409 if exc.code == 'busy' else 400)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse({'detail': '输入格式不正确，请检查链接、必填内容及时间范围。'}, status_code=422)

    def get(identifier):
        doc = store.get(identifier) if re.fullmatch(r'[a-f0-9]{32}', identifier) else None
        if not doc:
            raise HTTPException(404, '没有找到这条分析记录。')
        return doc

    def available():
        if pipeline.active_id:
            raise AnalysisError('busy', '已有视频正在分析，请等待当前任务完成。')

    @app.get('/api/health')
    def health():
        try:
            ffmpeg()
            media_available = True
        except AnalysisError:
            media_available = False
        return {'configured': not settings.missing, 'missing': settings.missing, 'media_available': media_available,
                'vision_model': settings.vision_model, 'asr_model': settings.asr_model,
                'max_duration': MAX_DURATION, 'max_bytes': MAX_BYTES, 'active_id': pipeline.active_id}

    @app.get('/api/analyses')
    def analyses():
        return [{key: value for key, value in public(doc).items() if key not in ('transcript', 'shots', 'overview')}
                for doc in store.list()]

    @app.post('/api/analyses', status_code=202)
    def create_link(body: LinkInput):
        available()
        url = extract_url(body.text)
        doc = store.create('抖音视频', url, 'douyin')
        try:
            pipeline.submit(doc['id'])
        except AnalysisError:
            store.delete(doc['id'])
            raise
        return public(store.get(doc['id']))

    async def accept_upload(file, identifier=None):
        available()
        filename = file.filename or '视频.mp4'
        suffix = Path(filename).suffix.lower()
        if suffix not in ('.mp4', '.mov'):
            raise AnalysisError('invalid_video', '请上传 MP4 或 MOV 格式的视频。')
        existing = get(identifier) if identifier else None
        if existing and existing['status'] != 'failed':
            raise HTTPException(409, '只有失败的任务可以替换视频来源。')
        doc = existing or store.create(Path(filename).stem[:200] or '上传视频')
        folder = settings.data_dir / doc['id']
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / f'upload-pending{suffix}'
        try:
            size = 0
            with temporary.open('wb') as target:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_BYTES:
                        raise AnalysisError('too_large', '文件超过200MB，请压缩后上传。')
                    target.write(chunk)
            # Decode metadata before accepting a task or invoking any AI service.
            import asyncio
            metadata = await asyncio.to_thread(probe, temporary)
            available()
            source = folder / f'source{suffix}'
            temporary.replace(source)
            store.update(doc['id'], title=Path(filename).stem[:200] or '上传视频', source_type='upload',
                         _cache={'source': source.name}, duration=metadata['duration'], width=metadata['width'],
                         height=metadata['height'], transcript=[], shots=[], overview=None, warnings=[], progress=0,
                         stage='preparing', error=None)
            pipeline.submit(doc['id'])
        except Exception:
            temporary.unlink(missing_ok=True)
            if not existing:
                store.delete(doc['id'])
                shutil.rmtree(folder, ignore_errors=True)
            raise
        finally:
            await file.close()
        return public(store.get(doc['id']))

    @app.post('/api/analyses/upload', status_code=202)
    async def upload(file: UploadFile = File(...)):
        return await accept_upload(file)

    @app.post('/api/analyses/{identifier}/upload', status_code=202)
    async def replace_video(identifier: str, file: UploadFile = File(...)):
        return await accept_upload(file, identifier)

    @app.get('/api/analyses/{identifier}')
    def analysis(identifier: str):
        return public(get(identifier))

    @app.patch('/api/analyses/{identifier}')
    def edit(identifier: str, body: EditInput):
        doc = get(identifier)
        if doc['status'] != 'completed':
            raise HTTPException(409, '分析完成后才能编辑结果。')
        if any(item.end > doc['duration'] + 0.001 for item in [*body.transcript, *body.shots]):
            raise HTTPException(422, '文案或分镜的结束时间不能超过视频时长。')
        for items in (body.transcript, body.shots):
            if len({item.id for item in items}) != len(items):
                raise HTTPException(422, '片段编号不能重复。')
            if any(items[i].start < items[i - 1].end for i in range(1, len(items))):
                raise HTTPException(422, '片段时间应按顺序排列且不能重叠。')
        thumbnails = {shot['id']: shot.get('thumbnail') for shot in doc['shots']}
        if {item.id for item in body.shots} != set(thumbnails):
            raise HTTPException(422, '分镜编号与原始记录不一致。')
        fields = body.model_dump()
        for shot in fields['shots']:
            shot['thumbnail'] = thumbnails.get(shot['id'])
        return public(store.update(identifier, **fields))

    @app.post('/api/analyses/{identifier}/retry', status_code=202)
    def retry(identifier: str):
        doc = get(identifier)
        if doc['status'] != 'failed':
            raise HTTPException(409, '当前记录无需重试。')
        pipeline.submit(identifier)
        return public(store.get(identifier))

    @app.delete('/api/analyses/{identifier}', status_code=204)
    def delete(identifier: str):
        doc = get(identifier)
        if pipeline.active_id == identifier or doc['status'] in ('running', 'queued'):
            raise HTTPException(409, '正在分析的记录暂时不能删除。')
        store.delete(identifier)
        shutil.rmtree(settings.data_dir / identifier, ignore_errors=True)
        return Response(status_code=204)

    @app.get('/api/analyses/{identifier}/export')
    def export(identifier: str, format: str = 'markdown'):
        doc = get(identifier)
        if doc['status'] != 'completed':
            raise HTTPException(409, '分析完成后才能导出。')
        if format not in ('markdown', 'csv'):
            raise HTTPException(422, '支持 Markdown 或 CSV 导出。')
        content = markdown(doc) if format == 'markdown' else storyboard_csv(doc)
        filename = quote(doc['title'] + ('.md' if format == 'markdown' else '-分镜.csv'), safe='')
        return Response(content, media_type='text/markdown; charset=utf-8' if format == 'markdown' else 'text/csv; charset=utf-8',
                        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{filename}"})

    @app.get('/api/analyses/{identifier}/media/{filename}')
    def media(identifier: str, filename: str):
        doc = get(identifier)
        allowed = {'video.mp4', 'cover.jpg'} | {frame['file'] for frame in doc['_cache'].get('frames', [])}
        path = settings.data_dir / identifier / filename
        if filename not in allowed or not path.is_file():
            raise HTTPException(404, '素材不存在。')
        return FileResponse(path, media_type='video/mp4' if filename.endswith('.mp4') else 'image/jpeg')

    dist = ROOT / 'frontend' / 'dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='frontend')
    return app


# Factory usage avoids creating data on import in tests.
if __name__ == '__main__':
    import os
    import uvicorn
    Settings()  # load .env before reading PORT
    uvicorn.run('backend.main:create_app', factory=True, host='127.0.0.1', port=int(os.getenv('PORT', '8765')))

