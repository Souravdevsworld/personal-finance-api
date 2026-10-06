import { useState, type ReactNode } from 'react'
import { NavLink, Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { Skeleton } from './ui'

const links = [['/dashboard', 'Dashboard'], ['/transactions', 'Transactions'], ['/budgets', 'Budgets'], ['/analytics', 'Analytics']]

export function ProtectedRoute() {
  const { isAuthenticated, loading } = useAuth()
  if (loading) return <div className="p-8"><Skeleton className="h-32" /></div>
  return isAuthenticated ? <Layout /> : <Navigate to="/login" replace />
}

function Layout() {
  const { email, logout } = useAuth()
  const [open, setOpen] = useState(false)
  const nav = (
    <nav className="flex h-full flex-col p-4 text-slate-300" aria-label="Main">
      <p className="mb-6 px-3 text-lg font-semibold text-white">Personal Finance</p>
      <ul className="space-y-1">
        {links.map(([to, label]) => (
          <li key={to}>
            <NavLink to={to} onClick={() => setOpen(false)}
              className={({ isActive }) => `flex min-h-[44px] items-center rounded-lg px-3 text-sm transition-colors ${isActive ? 'bg-white/10 text-white' : 'hover:bg-white/5'}`}>
              {label}
            </NavLink>
          </li>
        ))}
      </ul>
      <div className="mt-auto border-t border-white/10 pt-4">
        <p className="truncate px-3 text-xs text-slate-400">{email}</p>
        <button onClick={logout} className="mt-2 flex min-h-[44px] w-full items-center rounded-lg px-3 text-sm hover:bg-white/5">Log out</button>
      </div>
    </nav>
  )
  return (
    <div className="min-h-screen lg:flex">
      <aside className="hidden w-60 shrink-0 bg-ink lg:block"><div className="sticky top-0 h-screen">{nav}</div></aside>
      <header className="flex items-center justify-between bg-ink px-4 py-2 text-white lg:hidden">
        <span className="font-semibold">Personal Finance</span>
        <button className="min-h-[44px] rounded-lg px-3 text-sm hover:bg-white/10" aria-expanded={open} aria-label="Open menu" onClick={() => setOpen(true)}>Menu</button>
      </header>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" onClick={() => setOpen(false)}>
          <div className="absolute inset-0 bg-ink/50" />
          <div className="relative h-full w-64 bg-ink" onClick={(e) => e.stopPropagation()}>{nav}</div>
        </div>
      )}
      <main className="min-w-0 flex-1 p-4 sm:p-6 lg:p-8"><Outlet /></main>
    </div>
  )
}

export const PageHeader = ({ title, action }: { title: string; action?: ReactNode }) => (
  <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
    <h1 className="text-2xl font-semibold">{title}</h1>{action}
  </div>
)
