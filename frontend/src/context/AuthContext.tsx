import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { authApi } from '../api'
import { setUnauthorizedHandler, tokenStore } from '../api/client'

interface AuthState {
  token: string | null
  email: string | null
  isAuthenticated: boolean
  loading: boolean
  notice: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  logout: () => void
}
const Ctx = createContext<AuthState | null>(null)
const EMAIL_KEY = 'pf_email'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null)
  const [email, setEmail] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [notice, setNotice] = useState<string | null>(null)

  // Restore session. Token validity is confirmed by the backend on the first API call (401 => logout).
  useEffect(() => {
    setToken(tokenStore.get()); setEmail(localStorage.getItem(EMAIL_KEY)); setLoading(false)
  }, [])

  const logout = useCallback(() => {
    tokenStore.clear(); localStorage.removeItem(EMAIL_KEY); setToken(null); setEmail(null)
  }, [])

  useEffect(() => {
    setUnauthorizedHandler(() => { logout(); setNotice('Your session has expired. Please log in again.') })
  }, [logout])

  const login = useCallback(async (e: string, p: string) => {
    const t = await authApi.login(e, p)
    tokenStore.set(t.access_token); localStorage.setItem(EMAIL_KEY, e)
    setToken(t.access_token); setEmail(e); setNotice(null)
  }, [])

  const register = useCallback(async (e: string, p: string) => { await authApi.register(e, p) }, [])

  const value = useMemo(
    () => ({ token, email, isAuthenticated: !!token, loading, notice, login, register, logout }),
    [token, email, loading, notice, login, register, logout],
  )
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>
}

export const useAuth = () => {
  const c = useContext(Ctx)
  if (!c) throw new Error('useAuth must be used inside AuthProvider')
  return c
}
