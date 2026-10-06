import { useState, type FormEvent } from 'react'
import { analyticsApi, budgetsApi } from '../api'
import { PageHeader } from '../components/Layout'
import { Async, Card, Empty, Field, Modal, Skeleton, useToast } from '../components/ui'
import { BudgetProgress } from '../components/widgets'
import { useApi } from '../hooks/useApi'
import type { Budget } from '../types'
import { AMOUNT_ERROR, currentMonth, formatINR, formatMonth, isValidAmount } from '../utils/format'

type Mode = { kind: 'form'; b?: Budget } | { kind: 'delete'; b: Budget } | null

export default function Budgets() {
  const [month, setMonth] = useState(currentMonth())
  const list = useApi(budgetsApi.list, [])
  const bva = useApi(() => analyticsApi.budgetVsActual(month), [month])
  const [mode, setMode] = useState<Mode>(null)
  const toast = useToast()
  const done = (m: string) => { setMode(null); toast(m); list.reload(); bva.reload() }
  const add = <button className="btn-primary" onClick={() => setMode({ kind: 'form' })}>Create budget</button>

  return (
    <>
      <PageHeader title="Budgets" action={add} />
      <div className="space-y-4">
        <Card title="Budgets" action={<input aria-label="Month" type="month" className="input w-auto" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />}>
          <Async state={list} skeleton={<Skeleton className="h-32" />}>
            {(all) => {
              const rows = all.filter((b) => b.month.slice(0, 7) === month)
              if (!all.length) return <Empty text="You haven't created a budget yet." action={add} />
              if (!rows.length) return <Empty text={`No budgets for ${formatMonth(month)}.`} action={add} />
              return (
                <ul className="divide-y divide-slate-100">
                  {rows.map((b) => (
                    <li key={b.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
                      <span className="font-medium">{b.category}</span><span>{formatINR(b.amount)}</span>
                      <span className="flex gap-2"><button className="btn-ghost" onClick={() => setMode({ kind: 'form', b })}>Edit</button><button className="btn-ghost text-loss" onClick={() => setMode({ kind: 'delete', b })}>Delete</button></span>
                    </li>
                  ))}
                </ul>
              )
            }}
          </Async>
        </Card>
        <Card title={`Actual spending · ${formatMonth(month)}`}><Async state={bva} skeleton={<Skeleton className="h-32" />}>{(d) => <BudgetProgress data={d} />}</Async></Card>
      </div>
      {mode?.kind === 'form' && <BudgetForm b={mode.b} defaultMonth={month} onClose={() => setMode(null)} onSaved={() => done(mode.b ? 'Budget updated' : 'Budget created')} />}
      {mode?.kind === 'delete' && <ConfirmDelete b={mode.b} onClose={() => setMode(null)} onDeleted={() => done('Budget deleted')} />}
    </>
  )
}

function BudgetForm({ b, defaultMonth, onClose, onSaved }: { b?: Budget; defaultMonth: string; onClose: () => void; onSaved: () => void }) {
  const [category, setCategory] = useState(b?.category ?? ''), [amount, setAmount] = useState(b ? String(b.amount) : '')
  const [month, setMonth] = useState(b?.month.slice(0, 7) ?? defaultMonth)
  const [errs, setErrs] = useState<Record<string, string>>({}), [serverErr, setServerErr] = useState<string | null>(null), [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const v: Record<string, string> = {}
    if (!category.trim()) v.category = 'Category is required.'
    if (!isValidAmount(amount)) v.amount = AMOUNT_ERROR
    if (!month) v.month = 'Pick a month.'
    setErrs(v); if (Object.keys(v).length) return
    const body = { category: category.trim(), amount: amount.trim(), month }
    setBusy(true); setServerErr(null)
    try { b ? await budgetsApi.update(b.id, body) : await budgetsApi.create(body); onSaved() }
    catch (err) { setServerErr((err as Error).message); setBusy(false) }
  }
  return (
    <Modal title={b ? 'Edit budget' : 'Create budget'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        {serverErr && <p role="alert" className="rounded-lg bg-loss-soft p-3 text-sm text-loss">{serverErr}</p>}
        <Field label="Category" error={errs.category}><input className="input" maxLength={100} value={category} onChange={(e) => setCategory(e.target.value)} /></Field>
        <Field label="Amount (₹)" error={errs.amount}><input className="input" type="number" inputMode="decimal" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Month" error={errs.month}><input className="input" type="month" value={month} onChange={(e) => setMonth(e.target.value)} /></Field>
        <div className="flex gap-2 pt-2"><button type="button" className="btn-ghost flex-1" onClick={onClose}>Cancel</button><button className="btn-primary flex-1" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
      </form>
    </Modal>
  )
}

function ConfirmDelete({ b, onClose, onDeleted }: { b: Budget; onClose: () => void; onDeleted: () => void }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState<string | null>(null)
  const go = async () => { setBusy(true); try { await budgetsApi.remove(b.id); onDeleted() } catch (e) { setErr((e as Error).message); setBusy(false) } }
  return (
    <Modal title="Delete budget?" onClose={onClose}>
      <p className="text-sm text-slate-600">The {b.category} budget for {formatMonth(b.month)} will be permanently removed.</p>
      {err && <p role="alert" className="mt-3 rounded-lg bg-loss-soft p-3 text-sm text-loss">{err}</p>}
      <div className="mt-5 flex gap-2"><button className="btn-ghost flex-1" onClick={onClose}>Cancel</button><button className="btn-danger flex-1" disabled={busy} onClick={go}>{busy ? 'Deleting…' : 'Delete'}</button></div>
    </Modal>
  )
}
