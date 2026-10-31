export class ApiError extends Error {
  constructor(message, status = 0) {
    super(message)
    this.status = status
  }
}

export async function readApi(path, { signal, method = 'GET', body } = {}) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  signal?.addEventListener('abort', abort, { once: true })
  if (signal?.aborted) controller.abort()
  const timeout = setTimeout(abort, 10000)
  try {
    const response = await fetch(`/api${path}`, { signal: controller.signal, method,
      ...(body === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }) })
    let payload
    try { payload = await response.json() } catch { throw new ApiError('服务返回了无法读取的数据，请稍后重试。') }
    if (!response.ok) throw new ApiError(payload?.error?.message || '服务暂时不可用，请稍后重试。', response.status)
    return payload
  } catch (error) {
    if (signal?.aborted) throw error
    if (error instanceof ApiError) throw error
    throw new ApiError('服务暂时不可用，请稍后重试。')
  } finally {
    clearTimeout(timeout)
    signal?.removeEventListener('abort', abort)
  }
}
