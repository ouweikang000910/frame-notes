export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  let response: Response
  try { response = await fetch('/api' + path, options) }
  catch { throw new Error('无法连接本地服务，请检查启动终端是否仍在运行。') }
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(typeof body.detail === 'string' ? body.detail : '请求未完成，请稍后重试。')
  }
  if (response.status === 204) return undefined as T
  return response.json()
}

export function time(value: number) {
  return `${Math.floor(value / 60).toString().padStart(2, '0')}:${(value % 60).toFixed(1).padStart(4, '0')}`
}

export function shortDate(value: string) {
  return new Intl.DateTimeFormat('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', timeZone: 'Asia/Shanghai' }).format(new Date(value))
}
