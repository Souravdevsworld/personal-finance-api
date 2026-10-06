import { useState, type FormEvent } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Field } from '../components/ui'

export default function Auth({ mode }: { mode: 'login' | 'register' }) {
  const { isAuthenticated, login, register, notice } = useAuth()
  const nav = useNavigate()
  const [email, setEmail] = useState(''), [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null), [busy, setBusy] = useState(false)
  const isLogin = mode === 'login'
  if (isAuthenticated) return <Navigate to="/dashboard" replace />

  const submit = async (e: FormEvent) => {
    e.preventDefault(); setError(null); setBusy(true)
    try {
      if (isLogin) { await login(email, password); nav('/dashboard') }
      else { await register(email, password); nav('/login') }
    } catch (err) { setError((err as Error).message); setBusy(false) }
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-4 rounded-2xl border border-slate-200 bg-white p-6">
        <h1 className="text-xl font-semibold">{isLogin ? 'Log in' : 'Create your account'}</h1>
        {isLogin && notice && <p role="alert" className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800">{notice}</p>}
        {error && <p role="alert" className="rounded-lg bg-loss-soft p-3 text-sm text-loss">{error}</p>}
        <Field label="Email"><input className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Password"><input className="input" type="password" required minLength={isLogin ? undefined : 8} maxLength={isLogin ? undefined : 128} autoComplete={isLogin ? 'current-password' : 'new-password'} value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
        <button className="btn-primary w-full" disabled={busy}>{busy ? 'Please wait…' : isLogin ? 'Log in' : 'Create account'}</button>
        <p className="text-center text-sm text-slate-600">
          {isLogin ? <>No account? <Link className="underline" to="/register">Register</Link></> : <>Have an account? <Link className="underline" to="/login">Log in</Link></>}
        </p>
      </form>
    </div>
  )
}
