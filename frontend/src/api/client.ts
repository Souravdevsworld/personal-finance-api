const BASE = (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(/\/$/, '') ?? 'http://localhost:8000'
const TOKEN_KEY = 'pf_token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (t: string) => localStorage.setItem(TOKEN_KEY, t),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

let onUnauthorized: () => void = () => {}
export const setUnauthorizedHandler = (fn: () => void) => { onUnauthorized = fn }

function detailToMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) // FastAPI 422: [{loc, msg}]
    return detail.map((d) => `${(d.loc ?? []).slice(1).join('.') || 'input'}: ${d.msg}`).join('; ')
  return fallback
}

interface Opts { method?: string; body?: unknown; form?: URLSearchParams; query?: Record<string, string | number | undefined>; auth?: boolean }

export async function request<T>(path: string, { method = 'GET', body, form, query, auth = true }: Opts = {}): Promise<T> {
  const qs = new URLSearchParams()
  Object.entries(query ?? {}).forEach(([k, v]) => v !== undefined && v !== '' && qs.set(k, String(v)))
  const url = `${BASE}${path}${qs.toString() ? `?${qs}` : ''}`

  const headers: Record<string, string> = {}
  const token = tokenStore.get()
  if (auth && token) headers.Authorization = `Bearer ${token}`
  if (body !== undefined) headers['Content-Type'] = 'application/json'

  let res: Response
  try {
    res = await fetch(url, { method, headers, body: form ?? (body !== undefined ? JSON.stringify(body) : undefined) })
  } catch {
    throw new ApiError(0, 'Cannot reach the server. Check your connection and that the API is running (CORS must also allow this origin).')
  }

  if (res.status === 401 && auth && token) {
    onUnauthorized()
    throw new ApiError(401, 'Your session has expired. Please log in again.')
  }
  if (res.status === 204) return undefined as T

  const data = await res.json().catch(() => null)
  if (!res.ok) {
    const fallback = res.status >= 500 ? 'Something went wrong on the server. Please try again.' : `Request failed (${res.status}).`
    throw new ApiError(res.status, detailToMessage(data?.detail, fallback))
  }
  return data as T
}
