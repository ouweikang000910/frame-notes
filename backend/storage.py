import copy
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path):
        self.path = str(path)
        self.lock = threading.RLock()
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS analyses (id TEXT PRIMARY KEY, document TEXT NOT NULL)')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.execute('PRAGMA journal_mode=WAL')
        return db

    def create(self, title, source_url='', source_type='upload'):
        doc = dict(id=uuid.uuid4().hex, title=title, source_url=source_url, source_type=source_type,
                   status='queued', stage='acquiring', progress=0, message='正在准备视频', error=None,
                   created_at=now(), updated_at=now(), duration=0, width=0, height=0,
                   transcript=[], shots=[], overview=None, warnings=[], _cache={})
        with self.lock, self.connect() as db:
            db.execute('INSERT INTO analyses VALUES (?, ?)', (doc['id'], json.dumps(doc, ensure_ascii=False)))
        return doc

    def get(self, identifier):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT document FROM analyses WHERE id=?', (identifier,)).fetchone()
        return json.loads(row[0]) if row else None

    def update(self, identifier, **fields):
        with self.lock, self.connect() as db:
            row = db.execute('SELECT document FROM analyses WHERE id=?', (identifier,)).fetchone()
            if not row:
                return None
            doc = json.loads(row[0])
            doc.update(fields, updated_at=now())
            db.execute('UPDATE analyses SET document=? WHERE id=?', (json.dumps(doc, ensure_ascii=False), identifier))
        return doc

    def list(self):
        with self.lock, self.connect() as db:
            docs = [json.loads(row[0]) for row in db.execute('SELECT document FROM analyses')]
        return sorted(docs, key=lambda d: d['created_at'], reverse=True)

    def delete(self, identifier):
        with self.lock, self.connect() as db:
            db.execute('DELETE FROM analyses WHERE id=?', (identifier,))

    def recover_interrupted(self):
        for doc in self.list():
            if doc['status'] in ('queued', 'running'):
                self.update(doc['id'], status='failed', message='上次任务被中断，可继续重试',
                            error={'code': 'interrupted', 'message': '服务关闭时分析尚未完成，已保留阶段缓存。'})


def public(doc):
    result = copy.deepcopy(doc)
    result.pop('_cache', None)
    identifier = doc['id']
    result['video_url'] = f'/api/analyses/{identifier}/media/video.mp4' if doc.get('_cache', {}).get('prepared') else None
    result['cover_url'] = f'/api/analyses/{identifier}/media/cover.jpg' if doc.get('_cache', {}).get('prepared') else None
    for shot in result['shots']:
        if shot.get('thumbnail'):
            shot['thumbnail'] = f'/api/analyses/{identifier}/media/{shot["thumbnail"]}'
    return result

