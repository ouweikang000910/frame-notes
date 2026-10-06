import { useCallback, useEffect, useRef, useState } from 'react'
import { ArrowDownToLine, ArrowLeft, ArrowRight, Check, CheckCircle2, ChevronRight, CircleAlert, Clapperboard, Copy, FileText, Film, FolderOpen, History, Image, Layers3, Link2, LoaderCircle, PanelLeftClose, Play, Plus, RotateCcw, Save, Settings2, Sparkles, Trash2, Upload, X } from 'lucide-react'
import { api, shortDate, time } from './api'
import type { Analysis, Health, HistoryItem, Overview, Shot } from './types'

const labels: Record<Analysis['status'], string> = { queued: '准备中', running: '分析中', completed: '已完成', failed: '待处理' }
const stages = ['acquiring', 'preparing', 'transcribing', 'analyzing', 'summarizing', 'completed']
const stageLabels = ['获取视频', '视频预处理', '语音转写', '分镜分析', '整体汇总']
const overviewFields: { key: keyof Overview; label: string; hint: string }[] = [
  { key: 'topic', label: '视频主题', hint: '这条视频在讲什么' },
  { key: 'audience', label: '目标人群', hint: '内容在和谁对话' },
  { key: 'hook', label: '开头钩子', hint: '注意力从哪里开始' },
  { key: 'structure', label: '内容结构', hint: '故事如何层层展开' },
  { key: 'rhythm', label: '节奏特点', hint: '信息和画面的推进方式' },
  { key: 'observations', label: '视频观察', hint: '基于文案与画面的证据' },
  { key: 'takeaways', label: '创作参考', hint: '你可以借鉴的方法与建议' },
  { key: 'uncertainties', label: '待核对项', hint: '对照原视频进一步确认' },
]

export default function App() {
  const [history, setHistory] = useState<HistoryItem[]>([])
  const [health, setHealth] = useState<Health | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [draft, setDraft] = useState<Analysis | null>(null)
  const [dirty, setDirty] = useState(false)
  const [tab, setTab] = useState<'overview' | 'transcript' | 'shots'>('overview')
  const [toast, setToast] = useState<{ text: string; error: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<HistoryItem | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const videoRef = useRef<HTMLVideoElement>(null)
  const replacementRef = useRef<HTMLInputElement>(null)
  const activeId = useRef<string | null>(null)
  const dirtyRef = useRef(false)
  activeId.current = selectedId
  dirtyRef.current = dirty

  const notify = useCallback((text: string, error = false) => setToast({ text, error }), [])
  const refresh = useCallback(async () => {
    const [items, status] = await Promise.all([api<HistoryItem[]>('/analyses'), api<Health>('/health')])
    setHistory(items); setHealth(status)
  }, [])

  useEffect(() => {
    let disposed = false
    const poll = async () => {
      try {
        await refresh()
        const id = activeId.current
        if (id) {
          const doc = await api<Analysis>('/analyses/' + id)
          if (!disposed && activeId.current === id) {
            setAnalysis(doc)
            if (!dirtyRef.current) setDraft(doc)
          }
        }
      } catch (error) { if (!disposed) notify((error as Error).message, true) }
    }
    void poll()
    const interval = window.setInterval(poll, 2000)
    return () => { disposed = true; window.clearInterval(interval) }
  }, [refresh, notify])

  useEffect(() => {
    if (!toast) return
    const timeout = window.setTimeout(() => setToast(null), 5500)
    return () => window.clearTimeout(timeout)
  }, [toast])

  useEffect(() => {
    const onClose = (event: BeforeUnloadEvent) => { if (dirty) { event.preventDefault(); event.returnValue = '' } }
    window.addEventListener('beforeunload', onClose)
    return () => window.removeEventListener('beforeunload', onClose)
  }, [dirty])

  const select = async (id: string | null) => {
    if (dirty && !window.confirm('有尚未保存的修改，离开会丢弃这些修改。是否继续？')) return
    if (window.matchMedia('(max-width:620px)').matches) setSidebarOpen(true)
    setDirty(false); dirtyRef.current = false; setSelectedId(id); activeId.current = id
    setDraft(null); setAnalysis(null); setTab('overview')
    if (!id) return
    try {
      const doc = await api<Analysis>('/analyses/' + id)
      if (activeId.current === id) { setAnalysis(doc); setDraft(doc) }
    } catch (error) { notify((error as Error).message, true) }
  }

  const submitLink = async (text: string) => {
    setBusy(true)
    try {
      const doc = await api<Analysis>('/analyses', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text }) })
      await select(doc.id); await refresh()
    } catch (error) { notify((error as Error).message, true) }
    finally { setBusy(false) }
  }

  const submitFile = async (file: File, replacement = false) => {
    if (!/\.(mp4|mov)$/i.test(file.name)) { notify('请上传 MP4 或 MOV 格式的视频。', true); return }
    if (file.size > 200 * 1024 * 1024) { notify('文件超过200MB，请压缩后上传。', true); return }
    setBusy(true)
    try {
      const form = new FormData(); form.append('file', file)
      const path = replacement && selectedId ? `/analyses/${selectedId}/upload` : '/analyses/upload'
      const doc = await api<Analysis>(path, { method: 'POST', body: form })
      await select(doc.id); await refresh()
    } catch (error) { notify((error as Error).message, true) }
    finally { setBusy(false) }
  }

  const changeDraft = (update: (doc: Analysis) => Analysis) => {
    setDraft(current => current ? update(current) : current)
    setDirty(true); dirtyRef.current = true
  }

  const save = async () => {
    if (!draft) return
    setBusy(true)
    try {
      const doc = await api<Analysis>('/analyses/' + draft.id, { method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: draft.title, overview: draft.overview, transcript: draft.transcript, shots: draft.shots }) })
      setDraft(doc); setAnalysis(doc); setDirty(false); dirtyRef.current = false
      await refresh(); notify('修改已保存到本地')
    } catch (error) { notify((error as Error).message, true) }
    finally { setBusy(false) }
  }

  const download = async (format: 'markdown' | 'csv') => {
    if (!draft) return
    if (dirty) { notify('请先保存修改，再导出最新结果。', true); return }
    try {
      const response = await fetch(`/api/analyses/${draft.id}/export?format=${format}`)
      if (!response.ok) { const error = await response.json(); throw new Error(error.detail) }
      const blob = await response.blob(), url = URL.createObjectURL(blob), anchor = document.createElement('a')
      anchor.href = url; anchor.download = draft.title + (format === 'csv' ? '-分镜.csv' : '.md'); anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      notify(format === 'csv' ? '分镜表已导出，可用 Excel 打开' : 'Markdown报告已导出')
    } catch (error) { notify((error as Error).message, true) }
  }

  const retry = async () => {
    if (!selectedId) return
    setBusy(true)
    try { await api('/analyses/' + selectedId + '/retry', { method: 'POST' }); await select(selectedId); await refresh() }
    catch (error) { notify((error as Error).message, true) }
    finally { setBusy(false) }
  }

  const deleteRecord = async () => {
    if (!deleteTarget) return
    setBusy(true)
    try {
      await api('/analyses/' + deleteTarget.id, { method: 'DELETE' })
      if (selectedId === deleteTarget.id) { setDirty(false); dirtyRef.current = false; await select(null) }
      setDeleteTarget(null); await refresh(); notify('记录和本地素材已删除')
    } catch (error) { notify((error as Error).message, true) }
    finally { setBusy(false) }
  }

  const seek = (seconds: number) => {
    if (videoRef.current) { videoRef.current.currentTime = seconds; void videoRef.current.play().catch(() => {}) }
  }
  const copyTranscript = async () => {
    try { await navigator.clipboard.writeText((draft?.transcript || []).map(s => `${time(s.start)}–${time(s.end)} ${s.text}`).join('\n')); notify('文案已复制') }
    catch { notify('浏览器暂时无法复制，请手动选择文字复制。', true) }
  }
  const running = history.some(item => item.status === 'queued' || item.status === 'running')
  const completed = history.filter(item => item.status === 'completed').length

  return <div className={`app-shell ${sidebarOpen ? '' : 'sidebar-hidden'}`}>
    <aside className="sidebar">
      <button className="brand" onClick={() => void select(null)} aria-label="拆片首页"><span className="brand-symbol"><Clapperboard size={23} /></span><span><strong>拆片<span className="brand-dot">.</span></strong><small>FRAME NOTES</small></span></button>
      <button className="new-button" onClick={() => void select(null)}><Plus size={18} /> 新建拆解 <span>＋</span></button>
      <div className="history-heading"><span><History size={15} /> 拆解记录</span><b>{history.length}</b></div>
      <div className="history-list">
        {history.length === 0 ? <div className="history-empty"><FolderOpen size={25} /><p>从第一条视频开始</p><small>你的创作参考会留在这里</small></div> : history.map(item =>
          <div className={`history-row ${selectedId === item.id ? 'selected' : ''}`} key={item.id}>
            <button className="history-select" onClick={() => void select(item.id)}>
              <span className="history-icon">{item.status === 'running' || item.status === 'queued' ? <LoaderCircle size={17} className="spin" /> : <Film size={17} />}</span>
              <span><strong>{item.title}</strong><small>{shortDate(item.created_at)} <i className={`status-dot ${item.status}`} />{labels[item.status]}</small></span>
            </button>
            <button className="history-delete icon-button" title="删除记录" aria-label={`删除 ${item.title}`} disabled={['running', 'queued'].includes(item.status)} onClick={() => setDeleteTarget(item)}><Trash2 size={14} /></button>
          </div>)}
      </div>
      <div className="sidebar-footer"><div className="local-badge"><span /> 记录保存在本机</div><button onClick={() => setSettingsOpen(true)}><Settings2 size={16} /> 服务与设置 <ChevronRight size={15} /></button><small>观察好内容，积累好方法。</small></div>
    </aside>
    <div className="main-shell">
      <header className="topbar"><div><button className="icon-button" aria-label="切换侧栏" onClick={() => setSidebarOpen(v => !v)}><PanelLeftClose size={19} /></button><span className="breadcrumb">创作工具</span><ChevronRight size={13} /><strong>{selectedId ? '视频拆解工作台' : '视频拆解'}</strong></div><button className={`service-status ${health?.configured ? 'ready' : ''}`} onClick={() => setSettingsOpen(true)}><span />{health ? health.configured ? 'AI 服务已配置' : 'AI 服务待配置' : '连接本地服务…'}<Settings2 size={13} /></button></header>
      <main>
        {!selectedId ? <Home busy={busy || running} configured={!!health?.configured} count={completed} history={history} submitLink={submitLink} submitFile={submitFile} select={select} openSettings={() => setSettingsOpen(true)} /> : !draft ? <div className="loading-state"><LoaderCircle className="spin" />正在打开分析记录…</div> : <>
          <div className="workspace-heading"><div><button className="back-link" onClick={() => void select(null)}><ArrowLeft size={14} /> 返回首页</button><div className="editable-title"><input aria-label="视频标题" value={draft.title} disabled={draft.status !== 'completed'} onChange={e => changeDraft(doc => ({ ...doc, title: e.target.value }))} /><span className={`status-pill ${draft.status}`}>{labels[draft.status]}</span></div><p>{draft.source_type === 'douyin' ? '抖音视频' : '本地视频'}<span>·</span>{time(draft.duration)}<span>·</span>{shortDate(draft.created_at)}</p></div>
            {draft.status === 'completed' && <div className="workspace-actions"><button className="button secondary" disabled={busy || dirty} onClick={() => void download('markdown')}><ArrowDownToLine size={15} /> 报告</button><button className="button secondary" disabled={busy || dirty} onClick={() => void download('csv')}><Layers3 size={15} /> 分镜表</button><button className="button primary" onClick={() => void save()} disabled={busy || !dirty}>{busy ? <LoaderCircle size={15} className="spin" /> : dirty ? <Save size={15} /> : <Check size={15} />}{dirty ? '保存修改' : '已保存'}</button></div>}
          </div>
          {draft.status !== 'completed' && <div className={`progress-card ${draft.status === 'failed' ? 'failed' : ''}`}>
            <div className="progress-title">{draft.status === 'failed' ? <CircleAlert size={20} /> : <LoaderCircle size={20} className="spin" />}<div><strong>{draft.status === 'failed' ? '这一步需要处理' : '正在把视频拆成创作参考'}</strong><p>{draft.message}</p></div><span>{draft.progress}%</span></div>
            <div className="progress-track"><div style={{ width: `${draft.progress}%` }} /></div>
            <div className="stage-list">{stageLabels.map((label, i) => <span key={label} className={stages.indexOf(draft.stage) >= i ? 'active' : ''}>{stages.indexOf(draft.stage) > i ? <Check size={12} /> : <i>{i + 1}</i>}{label}</span>)}</div>
            {draft.status === 'failed' && <div className="failure-actions"><button className="button primary" disabled={busy || running} onClick={() => void retry()}><RotateCcw size={15} /> 从当前阶段重试</button>{draft.error?.code === 'not_configured' || draft.error?.code.startsWith('ai_') ? <button className="button secondary" onClick={() => setSettingsOpen(true)}><Settings2 size={15} /> 查看服务配置</button> : <button className="button secondary" disabled={busy || running} onClick={() => replacementRef.current?.click()}><Upload size={15} /> 上传视频继续分析</button>}<small>已完成的阶段会保留</small></div>}
          </div>}
          <input type="file" accept=".mp4,.mov,video/mp4,video/quicktime" className="visually-hidden" ref={replacementRef} onChange={e => { const file = e.target.files?.[0]; if (file) void submitFile(file, true); e.target.value = '' }} />
          <div className="workbench">
            <section className="video-panel"><div className="panel-heading"><span><Play size={15} /> 原视频</span><small>{draft.width ? `${draft.width} × ${draft.height}` : '等待获取'}</small></div>
              <div className="video-stage">{draft.video_url ? <video key={draft.video_url} ref={videoRef} src={draft.video_url} poster={draft.cover_url || undefined} controls preload="metadata" /> : <div className="video-placeholder"><Film size={42} /><p>视频准备好后会显示在这里</p><small>你可以对照时间戳核对拆解结果</small></div>}</div>
              <div className="video-footnote"><span><Link2 size={14} />{draft.source_url ? <a href={draft.source_url} target="_blank" rel="noreferrer">查看原始链接</a> : '本地上传素材'}</span><span>点击分析中的时间戳可跳转</span></div>
              <div className="note-card"><Sparkles size={17} /><div><strong>把观察变成创作方法</strong><p>AI 结果供你参考。对照画面核对细节，再把值得借鉴的方法留给下一次创作。</p></div></div>
              {draft.warnings.map(warning => <div className="warning-note" key={warning}><CircleAlert size={15} />{warning}</div>)}
            </section>
            <section className="analysis-panel"><div className="tabs" role="tablist">{([{ key: 'overview', label: '整体分析', icon: Sparkles }, { key: 'transcript', label: '文案', icon: FileText }, { key: 'shots', label: '分镜', icon: Layers3 }] as const).map(({ key, label, icon: Icon }) => <button role="tab" aria-selected={tab === key} key={key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}><Icon size={16} />{label}{key !== 'overview' && <small>{key === 'transcript' ? draft.transcript.length : draft.shots.length}</small>}</button>)}{dirty && <span className="unsaved">未保存</span>}</div>
              <div className="analysis-content">
                {tab === 'overview' && (draft.overview ? <div className="overview-grid">{overviewFields.map(({ key, label, hint }, index) => <div key={key} className={`overview-item field-${key}`}><div className="field-heading"><span className="field-number">{String(index + 1).padStart(2, '0')}</span><div><h3>{label}</h3><small>{hint}</small></div>{key === 'takeaways' && <span className="suggestion-badge">创作建议</span>}</div><AutoText label={label} value={draft.overview![key]} disabled={draft.status !== 'completed'} onChange={value => changeDraft(doc => ({ ...doc, overview: { ...doc.overview!, [key]: value } }))} /></div>)}</div> : <AnalysisEmpty icon={<Sparkles />} title="整体分析正在酝酿" text="分镜拆解完成后，AI会汇总钩子、结构和创作方法。" />)}
                {tab === 'transcript' && <><div className="list-heading"><p>带时间戳的逐句文案 <small>· 可直接修改文字</small></p><button className="text-button" disabled={!draft.transcript.length} onClick={() => void copyTranscript()}><Copy size={14} />复制文案</button></div>{draft.transcript.length ? draft.transcript.map((sentence, index) => <div className="sentence-card" key={sentence.id}><div className="sentence-meta"><span className="field-number">{String(index + 1).padStart(2, '0')}</span><button className="time-link" onClick={() => seek(sentence.start)}><Play size={11} />{time(sentence.start)}</button><span>—</span><span>{time(sentence.end)}</span></div><AutoText label={`第${index + 1}句文案`} value={sentence.text} disabled={draft.status !== 'completed'} onChange={value => changeDraft(doc => ({ ...doc, transcript: doc.transcript.map(s => s.id === sentence.id ? { ...s, text: value } : s) }))} /></div>) : <AnalysisEmpty icon={<FileText />} title={['completed', 'analyzing', 'summarizing'].includes(draft.stage) ? '未识别到语音' : '文案将在转写后显示'} text="没有语音的视频仍可通过画面进行拆解。" />}</>}
                {tab === 'shots' && <><div className="list-heading"><p>画面、文案与段落作用 <small>· 点击缩略图播放</small></p></div>{draft.shots.length ? draft.shots.map((shot, index) => <ShotCard key={shot.id} shot={shot} index={index} duration={draft.duration} disabled={draft.status !== 'completed'} seek={seek} update={patch => changeDraft(doc => ({ ...doc, shots: doc.shots.map(s => s.id === shot.id ? { ...s, ...patch } : s) }))} />) : <AnalysisEmpty icon={<Layers3 />} title="分镜将在画面分析后显示" text="每段包含画面观察、对应文案、段落作用和节奏。" />}</>}
              </div>
            </section>
          </div>
        </>}
      </main>
      <footer className="page-footer"><span>FRAME NOTES <i>/</i> 每一次拆解，都为下一次创作。</span><span>本地工作台 · V1.0</span></footer>
    </div>
    {toast && <div className={`toast ${toast.error ? 'error' : ''}`} role="status">{toast.error ? <CircleAlert size={18} /> : <CheckCircle2 size={18} />}{toast.text}<button className="icon-button" aria-label="关闭提示" onClick={() => setToast(null)}><X size={15} /></button></div>}
    {settingsOpen && <Modal title="服务与本地设置" close={() => setSettingsOpen(false)}><div className="settings-state"><span className={`status-dot ${health?.configured ? 'completed' : 'failed'}`} /><strong>{health?.configured ? '百炼配置已就绪' : '配置百炼，开启 AI 拆解'}</strong></div><p className="modal-description">在项目根目录将 <code>.env.example</code> 复制为 <code>.env</code>，填写北京地域的服务信息，然后重启工具。</p><pre>DASHSCOPE_API_KEY=你的 API Key{'\n'}BAILIAN_WORKSPACE_ID=你的 Workspace ID</pre><div className="settings-detail"><div><span>语音识别</span><code>{health?.asr_model || 'fun-asr-realtime'}</code></div><div><span>视觉与结构分析</span><code>{health?.vision_model || 'qwen3.6-flash'}</code></div><div><span>视频处理</span><strong>{health?.media_available ? 'FFmpeg 已就绪' : '请运行安装脚本'}</strong></div><div><span>处理范围</span><strong>单条 · 5分钟以内 · 200MB以内</strong></div></div><p className="privacy-note">视频与记录保存在本机。分析时，音频及抽帧会发送给百炼，模型调用按服务实际用量计费。</p><div className="modal-actions"><a className="button secondary" href="https://bailian.console.aliyun.com/" target="_blank" rel="noreferrer">打开百炼控制台 <ArrowRight size={14} /></a><button className="button primary" onClick={() => setSettingsOpen(false)}>知道了</button></div></Modal>}
    {deleteTarget && <Modal title="删除这条拆解记录？" close={() => setDeleteTarget(null)}><p className="modal-description">“{deleteTarget.title}”的分析结果、视频和缩略图将从本机删除，此操作无法撤销。</p><div className="modal-actions"><button className="button secondary" onClick={() => setDeleteTarget(null)}>保留记录</button><button className="button danger" disabled={busy} onClick={() => void deleteRecord()}><Trash2 size={15} />删除记录</button></div></Modal>}
  </div>
}

function Home({ busy, configured, count, history, submitLink, submitFile, select, openSettings }: { busy: boolean; configured: boolean; count: number; history: HistoryItem[]; submitLink: (text: string) => Promise<void>; submitFile: (file: File) => Promise<void>; select: (id: string | null) => Promise<void>; openSettings: () => void }) {
  const [text, setText] = useState(''), [dragging, setDragging] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  return <div className="home">
    <div className="hero"><div className="eyebrow"><span /> YOUR NEXT IDEA STARTS HERE</div><h1>把好视频，<br />拆成你的<span className="highlight">创作方法<svg viewBox="0 0 270 16" aria-hidden="true"><path d="M2 10 Q100 -2 268 9 M40 15 Q150 4 253 13" /></svg></span>。</h1><p>看懂开头的吸引力，梳理文案与画面。<br className="mobile-break" />让每一个值得借鉴的细节，都有迹可循。</p><div className="hero-decoration" aria-hidden="true"><div className="decoration-frame frame-back" /><div className="decoration-frame frame-front"><span>FRAME / 01</span><div><Play fill="currentColor" size={26} /></div><i>00:00 <b /><b /><b /><b /><b /> 00:30</i></div><span className="decoration-note"><Sparkles size={13} /> 找到内容的骨架</span><span className="orbit-dot" /></div></div>
    <div className="ingest-grid"><section className="ingest-card"><div className="card-title"><span className="title-icon"><Link2 size={19} /></span><div><h2>从一条视频开始</h2><p>粘贴抖音链接，或直接粘贴完整分享文本</p></div><span className="tiny-badge">抖音</span></div><form onSubmit={e => { e.preventDefault(); if (text.trim()) void submitLink(text.trim()) }}><textarea aria-label="抖音链接或分享文本" placeholder={"粘贴 https://v.douyin.com/…\n也支持「复制链接」得到的完整分享文本"} value={text} onChange={e => setText(e.target.value)} disabled={busy} /><div className="ingest-bottom"><span><CheckCircle2 size={13} /> 短链接 / 视频详情 / 分享文本</span><button className="button primary" disabled={busy || !text.trim()} type="submit">{busy ? <LoaderCircle size={16} className="spin" /> : <Sparkles size={16} />}{busy ? '正在处理' : '开始拆解'}{!busy && <ArrowRight size={16} />}</button></div></form><div className="separator"><span>或者，使用本地视频</span></div><button className={`upload-zone ${dragging ? 'dragging' : ''}`} disabled={busy} onClick={() => fileRef.current?.click()} onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); const file = e.dataTransfer.files[0]; if (file && !busy) void submitFile(file) }}><span className="upload-icon"><Upload size={21} /></span><div><strong>点击上传，或把视频拖到这里</strong><small>MP4 / MOV <i>·</i> 5分钟以内 <i>·</i> 最大200MB</small></div><Plus size={18} /></button><input ref={fileRef} type="file" className="visually-hidden" accept=".mp4,.mov,video/mp4,video/quicktime" onChange={e => { const file = e.target.files?.[0]; if (file) void submitFile(file); e.target.value = '' }} />{!configured && <button className="config-prompt" onClick={openSettings}><CircleAlert size={14} /><span>首次使用，先配置 AI 服务</span><ArrowRight size={14} /></button>}</section>
    <aside className="dimensions-card"><div className="dimensions-heading"><span>一条视频，三层拆解</span><Sparkles size={17} /></div><div className="dimension"><span className="dimension-icon mint"><Sparkles size={19} /></span><div><h3>看懂内容结构</h3><p>主题、人群、开头钩子<br />以及内容层层推进的方式</p></div><span className="dimension-index">01</span></div><div className="dimension"><span className="dimension-icon peach"><FileText size={19} /></span><div><h3>还原逐句文案</h3><p>带时间戳的语音转写<br />点一下，回到对应的那句话</p></div><span className="dimension-index">02</span></div><div className="dimension"><span className="dimension-icon lavender"><Layers3 size={19} /></span><div><h3>拆开画面与节奏</h3><p>分镜、段落作用与剪辑节奏<br />把抽象感受变成具体参考</p></div><span className="dimension-index">03</span></div><div className="dimension-foot"><span><Save size={13} /> 可编辑保存</span><span><ArrowDownToLine size={13} /> 报告 / 分镜表</span></div></aside></div>
    <section className="recent-section"><div className="section-heading"><div><h2>你的拆解积累 <span>{count.toString().padStart(2, '0')}</span></h2><p>留下观察，积累属于自己的创作方法。</p></div><span className="local-caption"><span /> 保存在本机</span></div>{history.length ? <div className="recent-grid">{history.slice(0, 6).map(item => <button className="recent-card" onClick={() => void select(item.id)} key={item.id}><div className="recent-cover">{item.cover_url ? <img src={item.cover_url} alt="视频封面" /> : <Film size={25} />}<span className={`status-pill ${item.status}`}>{labels[item.status]}</span>{item.duration > 0 && <span className="duration">{time(item.duration)}</span>}</div><div><h3>{item.title}</h3><p>{shortDate(item.created_at)}<ArrowRight size={15} /></p></div></button>)}</div> : <div className="empty-library"><span className="empty-library-icon"><FolderOpen size={25} /></span><div><h3>第一份创作参考，等你开启</h3><p>分析完成后，视频、文案和分镜会保存在这里。</p></div><div className="empty-library-motif" aria-hidden="true"><i /><i /><i /></div></div>}</section>
  </div>
}

function AutoText({ label, value, disabled, onChange }: { label: string; value: string; disabled?: boolean; onChange: (value: string) => void }) {
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { if (ref.current) { ref.current.style.height = 'auto'; ref.current.style.height = ref.current.scrollHeight + 'px' } }, [value])
  return <textarea ref={ref} className="editable-text" aria-label={label} value={value} disabled={disabled} onChange={event => onChange(event.target.value)} rows={2} />
}

function ShotCard({ shot, index, duration, disabled, seek, update }: { shot: Shot; index: number; duration: number; disabled: boolean; seek: (time: number) => void; update: (patch: Partial<Shot>) => void }) {
  return <article className="shot-card"><div className="shot-top"><span className="shot-index">分镜 {String(index + 1).padStart(2, '0')}</span><button className="time-link" onClick={() => seek(shot.start)}><Play size={11} />{time(shot.start)} — {time(shot.end)}</button><label className="uncertain-toggle"><input type="checkbox" checked={shot.uncertain} disabled={disabled} onChange={e => update({ uncertain: e.target.checked })} />待核对</label></div><div className="shot-body"><div className="shot-media"><button className="thumbnail-button" onClick={() => seek(shot.start)} aria-label={`播放分镜${index + 1}`}>{shot.thumbnail ? <img src={shot.thumbnail} alt={`分镜${index + 1}画面`} /> : <Image size={25} />}<span><Play fill="currentColor" size={17} /></span></button><div className="shot-times"><label>开始 / 秒<input type="number" step="0.1" min="0" max={duration} aria-label={`分镜${index + 1}开始秒数`} disabled={disabled} value={shot.start} onChange={e => update({ start: Number(e.target.value) })} /></label><label>结束 / 秒<input type="number" step="0.1" min="0" max={duration} aria-label={`分镜${index + 1}结束秒数`} disabled={disabled} value={shot.end} onChange={e => update({ end: Number(e.target.value) })} /></label></div></div><div className="shot-fields">{([{ key: 'description', label: '画面观察' }, { key: 'text', label: '对应文案' }, { key: 'role', label: '段落作用' }, { key: 'rhythm', label: '节奏分析' }] as const).map(({ key, label }) => <div key={key}><label>{label}</label><AutoText label={`分镜${index + 1}${label}`} value={shot[key]} disabled={disabled} onChange={value => update({ [key]: value })} /></div>)}</div></div></article>
}

function AnalysisEmpty({ icon, title, text }: { icon: React.ReactNode; title: string; text: string }) { return <div className="analysis-empty"><span>{icon}</span><h3>{title}</h3><p>{text}</p></div> }
function Modal({ title, close, children }: { title: string; close: () => void; children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null)
  const closeRef = useRef(close)
  closeRef.current = close
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null
    const elements = () => Array.from(ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]), a[href], input, textarea') || [])
    elements()[0]?.focus()
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeRef.current()
      if (event.key === 'Tab') { const all = elements(), first = all[0], last = all.at(-1); if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() } }
    }
    document.addEventListener('keydown', key)
    return () => { document.removeEventListener('keydown', key); previous?.focus() }
  }, [])
  return <div className="modal-backdrop" onClick={close}><div className="modal" ref={ref} role="dialog" aria-modal="true" aria-label={title} onClick={e => e.stopPropagation()}><div className="modal-heading"><h2>{title}</h2><button className="icon-button" onClick={close} aria-label="关闭窗口"><X size={19} /></button></div>{children}</div></div>
}
