import { useState, type FormEvent } from 'react'
import { transactionsApi } from '../api'
import { PageHeader } from '../components/Layout'
import { Amount, TypeBadge } from '../components/widgets'
import { Async, Card, Empty, Field, Modal, Skeleton, useToast } from '../components/ui'
import { useApi } from '../hooks/useApi'
import type { Transaction, TransactionInput, TransactionType } from '../types'
import { AMOUNT_ERROR, formatDate, formatINR, isValidAmount, today } from '../utils/format'

type Mode = { kind: 'form'; tx?: Transaction } | { kind: 'view'; id: number } | { kind: 'delete'; tx: Transaction } | null

export default function Transactions() {
  const list = useApi(transactionsApi.list, [])
  const [mode, setMode] = useState<Mode>(null)
  const toast = useToast()
  const done = (msg: string) => { setMode(null); toast(msg); list.reload() }
  const addBtn = <button className="btn-primary" onClick={() => setMode({ kind: 'form' })}>Add transaction</button>

  return (
    <>
      <PageHeader title="Transactions" action={addBtn} />
      <Card>
        <Async state={list} skeleton={<div className="space-y-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-12" />)}</div>}
          empty={(d) => d.length ? null : <Empty text="You don't have any transactions yet." action={addBtn} />}>
          {(d) => (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-left text-sm">
                <thead className="text-slate-500"><tr><th className="py-2 font-normal">Date</th><th className="font-normal">Category</th><th className="font-normal">Type</th><th className="font-normal">Description</th><th className="text-right font-normal">Amount</th></tr></thead>
                <tbody>
                  {[...d].sort((a, b) => b.transaction_date.localeCompare(a.transaction_date)).map((t) => (
                    <tr key={t.id} className="border-t border-slate-100">
                      <td className="whitespace-nowrap py-2.5">{formatDate(t.transaction_date)}</td>
                      <td><button className="underline decoration-slate-300 underline-offset-2" onClick={() => setMode({ kind: 'view', id: t.id })}>{t.category}</button></td>
                      <td><TypeBadge type={t.transaction_type} /></td>
                      <td className="max-w-[200px] truncate text-slate-600">{t.description}</td>
                      <td className="text-right"><Amount t={t} /></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Async>
      </Card>

      {mode?.kind === 'form' && <TxForm tx={mode.tx} onClose={() => setMode(null)} onSaved={() => done(mode.tx ? 'Transaction updated' : 'Transaction added')} />}
      {mode?.kind === 'view' && <TxDetail id={mode.id} onClose={() => setMode(null)} onEdit={(tx) => setMode({ kind: 'form', tx })} onDelete={(tx) => setMode({ kind: 'delete', tx })} />}
      {mode?.kind === 'delete' && <ConfirmDelete tx={mode.tx} onClose={() => setMode(null)} onDeleted={() => done('Transaction deleted')} />}
    </>
  )
}

function TxDetail({ id, onClose, onEdit, onDelete }: { id: number; onClose: () => void; onEdit: (t: Transaction) => void; onDelete: (t: Transaction) => void }) {
  const q = useApi(() => transactionsApi.get(id), [id])
  return (
    <Modal title="Transaction details" onClose={onClose}>
      <Async state={q} skeleton={<Skeleton className="h-32" />}>
        {(t) => (
          <>
            <dl className="space-y-2 text-sm">
              <div className="flex justify-between"><dt className="text-slate-500">Amount</dt><dd><Amount t={t} /></dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Type</dt><dd><TypeBadge type={t.transaction_type} /></dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Category</dt><dd>{t.category}</dd></div>
              <div className="flex justify-between"><dt className="text-slate-500">Date</dt><dd>{formatDate(t.transaction_date)}</dd></div>
              <div><dt className="text-slate-500">Description</dt><dd>{t.description || '—'}</dd></div>
            </dl>
            <div className="mt-5 flex gap-2"><button className="btn-ghost flex-1" onClick={() => onEdit(t)}>Edit</button><button className="btn-danger flex-1" onClick={() => onDelete(t)}>Delete</button></div>
          </>
        )}
      </Async>
    </Modal>
  )
}

function TxForm({ tx, onClose, onSaved }: { tx?: Transaction; onClose: () => void; onSaved: () => void }) {
  const [amount, setAmount] = useState(tx ? String(tx.amount) : '')
  const [type, setType] = useState<TransactionType>(tx?.transaction_type ?? 'expense')
  const [category, setCategory] = useState(tx?.category ?? '')
  const [description, setDescription] = useState(tx?.description ?? '')
  const [date, setDate] = useState(tx?.transaction_date.slice(0, 10) ?? today())
  const [errs, setErrs] = useState<Record<string, string>>({}), [serverErr, setServerErr] = useState<string | null>(null), [busy, setBusy] = useState(false)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    const v: Record<string, string> = {}
    if (!isValidAmount(amount)) v.amount = AMOUNT_ERROR
    if (category.trim().length > 100) v.category = 'Category must be 100 characters or fewer.'
    if (!category.trim()) v.category = 'Category is required.'
    if (!date) v.date = 'Pick a date.'
    setErrs(v); if (Object.keys(v).length) return
    const body: TransactionInput = { amount: amount.trim(), transaction_type: type, category: category.trim(), description: description.trim() || null, transaction_date: date }
    setBusy(true); setServerErr(null)
    try { tx ? await transactionsApi.update(tx.id, body) : await transactionsApi.create(body); onSaved() }
    catch (err) { setServerErr((err as Error).message); setBusy(false) }
  }

  return (
    <Modal title={tx ? 'Edit transaction' : 'Add transaction'} onClose={onClose}>
      <form onSubmit={submit} className="space-y-3" noValidate>
        {serverErr && <p role="alert" className="rounded-lg bg-loss-soft p-3 text-sm text-loss">{serverErr}</p>}
        <Field label="Type"><select className="input" value={type} onChange={(e) => setType(e.target.value as TransactionType)}><option value="expense">Expense</option><option value="income">Income</option></select></Field>
        <Field label="Amount (₹)" error={errs.amount}><input className="input" inputMode="decimal" type="number" step="0.01" min="0" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
        <Field label="Category" error={errs.category}><input className="input" maxLength={100} value={category} onChange={(e) => setCategory(e.target.value)} /></Field>
        <Field label="Date" error={errs.date}><input className="input" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
        <Field label="Description (optional)"><input className="input" maxLength={500} value={description} onChange={(e) => setDescription(e.target.value)} /></Field>
        <div className="flex gap-2 pt-2"><button type="button" className="btn-ghost flex-1" onClick={onClose}>Cancel</button><button className="btn-primary flex-1" disabled={busy}>{busy ? 'Saving…' : 'Save'}</button></div>
      </form>
    </Modal>
  )
}

function ConfirmDelete({ tx, onClose, onDeleted }: { tx: Transaction; onClose: () => void; onDeleted: () => void }) {
  const [busy, setBusy] = useState(false), [err, setErr] = useState<string | null>(null)
  const go = async () => { setBusy(true); try { await transactionsApi.remove(tx.id); onDeleted() } catch (e) { setErr((e as Error).message); setBusy(false) } }
  return (
    <Modal title="Delete transaction?" onClose={onClose}>
      <p className="text-sm text-slate-600">{tx.category} · {formatINR(tx.amount)} on {formatDate(tx.transaction_date)} will be permanently removed.</p>
      {err && <p role="alert" className="mt-3 rounded-lg bg-loss-soft p-3 text-sm text-loss">{err}</p>}
      <div className="mt-5 flex gap-2"><button className="btn-ghost flex-1" onClick={onClose}>Cancel</button><button className="btn-danger flex-1" disabled={busy} onClick={go}>{busy ? 'Deleting…' : 'Delete'}</button></div>
    </Modal>
  )
}
