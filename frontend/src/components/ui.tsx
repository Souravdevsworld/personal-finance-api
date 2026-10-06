import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

export const Card = ({ title, action, children, className = '' }: { title?: string; action?: ReactNode; children: ReactNode; className?: string }) => (
  <section className={`rounded-xl border border-slate-200 bg-white p-4 sm:p-5 ${className}`}>
    {(title || action) && (
      <header className="mb-4 flex flex-wrap items-center justify-between gap-2">
        {title && <h2 className="text-base font-semibold">{title}</h2>}
        {action}
      </header>
    )}
    {children}
  </section>
)

export const Skeleton = ({ className = 'h-24' }: { className?: string }) => (
  <div className={`animate-pulse rounded-lg bg-slate-200/70 ${className}`} aria-hidden="true" />
)

export const ErrorBox = ({ message, onRetry }: { message: string; onRetry?: () => void }) => (
  <div role="alert" className="rounded-lg border border-loss/30 bg-loss-soft p-4 text-sm text-loss">
    <p>{message}</p>
    {onRetry && <button onClick={onRetry} className="btn-ghost mt-3">Retry</button>}
  </div>
)

export const Empty = ({ text, action }: { text: string; action?: ReactNode }) => (
  <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed border-slate-300 px-4 py-10 text-center text-sm text-slate-600">
    <p>{text}</p>{action}
  </div>
)

/** Wraps loading / error / empty handling so pages stay small. */
export function Async<T>({ state, empty, skeleton, children }: {
  state: { data: T | null; loading: boolean; error: string | null; reload: () => void }
  empty?: (d: T) => ReactNode | null
  skeleton?: ReactNode
  children: (d: T) => ReactNode
}) {
  if (state.loading && !state.data) return <>{skeleton ?? <Skeleton className="h-40" />}</>
  if (state.error) return <ErrorBox message={state.error} onRetry={state.reload} />
  if (!state.data) return null
  return <>{empty?.(state.data) ?? children(state.data)}</>
}

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const h = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-ink/50 p-0 sm:items-center sm:p-4" onMouseDown={onClose}>
      <div role="dialog" aria-modal="true" aria-label={title} onMouseDown={(e) => e.stopPropagation()}
        className="max-h-[92vh] w-full max-w-md overflow-y-auto rounded-t-2xl bg-white p-5 shadow-xl sm:rounded-2xl">
        <h2 className="mb-4 text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  )
}

export const Field = ({ label, error, children }: { label: string; error?: string; children: ReactNode }) => (
  <label className="block">
    <span className="mb-1 block text-sm font-medium">{label}</span>
    {children}
    {error && <span role="alert" className="mt-1 block text-sm text-loss">{error}</span>}
  </label>
)

interface Toast { id: number; text: string; kind: 'ok' | 'err' }
const ToastCtx = createContext<(text: string, kind?: Toast['kind']) => void>(() => {})
export const useToast = () => useContext(ToastCtx)
export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<Toast[]>([])
  const push = useCallback((text: string, kind: Toast['kind'] = 'ok') => {
    const id = Date.now() + Math.random()
    setItems((s) => [...s, { id, text, kind }])
    setTimeout(() => setItems((s) => s.filter((t) => t.id !== id)), 3500)
  }, [])
  return (
    <ToastCtx.Provider value={push}>
      {children}
      <div className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2" aria-live="polite">
        {items.map((t) => (
          <div key={t.id} className={`rounded-lg px-4 py-3 text-sm text-white shadow-lg ${t.kind === 'ok' ? 'bg-gain' : 'bg-loss'}`}>{t.text}</div>
        ))}
      </div>
    </ToastCtx.Provider>
  )
}
