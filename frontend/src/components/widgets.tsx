import type { BudgetVsActual, CategoryExpense, MonthlyTrend, SavingsRate, Summary, Transaction } from '../types'
import { formatDate, formatINR, formatMonth, formatPercent, num } from '../utils/format'
import { Empty } from './ui'

export const TypeBadge = ({ type }: { type: Transaction['transaction_type'] }) => (
  <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium ${type === 'income' ? 'bg-gain-soft text-gain' : 'bg-loss-soft text-loss'}`}>
    <span aria-hidden="true">{type === 'income' ? '↑' : '↓'}</span>{type === 'income' ? 'Income' : 'Expense'}
  </span>
)

export const Amount = ({ t }: { t: Pick<Transaction, 'amount' | 'transaction_type'> }) => (
  <span className={`font-medium ${t.transaction_type === 'income' ? 'text-gain' : 'text-loss'}`}>
    {t.transaction_type === 'income' ? '+' : '−'}{formatINR(t.amount)}
  </span>
)

export function SummaryCards({ s, rate }: { s: Summary; rate: SavingsRate | null }) {
  const items = [
    { label: 'Balance', value: formatINR(s.balance), tone: num(s.balance) >= 0 ? 'text-ink' : 'text-loss' },
    { label: 'Total income', value: formatINR(s.total_income), tone: 'text-gain' },
    { label: 'Total expenses', value: formatINR(s.total_expenses), tone: 'text-loss' },
    { label: 'Savings rate', value: rate ? formatPercent(rate.savings_rate) : '—', tone: 'text-ink' },
    { label: 'Transactions', value: String(s.transaction_count), tone: 'text-ink' },
  ]
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      {items.map((i, idx) => (
        <div key={i.label} className={`rounded-xl border border-slate-200 bg-white p-4 ${idx === 0 ? 'col-span-2 lg:col-span-1' : ''}`}>
          <p className="text-sm text-slate-500">{i.label}</p>
          <p className={`mt-1 text-xl font-semibold sm:text-2xl ${i.tone}`}>{i.value}</p>
        </div>
      ))}
    </div>
  )
}

export function TrendChart({ data }: { data: MonthlyTrend[] }) {
  if (!data.length) return <Empty text="Not enough financial data to display this chart." />
  const max = Math.max(...data.flatMap((d) => [num(d.income), num(d.expenses)]), 1)
  const W = 600, H = 220, pad = 24, slot = (W - pad * 2) / data.length, bw = Math.min(22, slot / 3)
  const y = (v: number) => H - pad - (v / max) * (H - pad * 2)
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="Monthly income and expenses">
        <line x1={pad} x2={W - pad} y1={H - pad} y2={H - pad} stroke="#cbd5e1" />
        {data.map((d, i) => {
          const cx = pad + slot * i + slot / 2
          return (
            <g key={d.month}>
              <rect x={cx - bw - 1} y={y(num(d.income))} width={bw} height={H - pad - y(num(d.income))} rx="3" fill="#0f8a5f">
                <title>{`${formatMonth(d.month)} income: ${formatINR(d.income)}`}</title>
              </rect>
              <rect x={cx + 1} y={y(num(d.expenses))} width={bw} height={H - pad - y(num(d.expenses))} rx="3" fill="#c2410c">
                <title>{`${formatMonth(d.month)} expenses: ${formatINR(d.expenses)}`}</title>
              </rect>
              <text x={cx} y={H - 6} textAnchor="middle" fontSize="11" fill="#64748b">{formatMonth(d.month)}</text>
            </g>
          )
        })}
      </svg>
      <p className="mt-2 flex gap-4 text-xs text-slate-600">
        <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-gain" />Income</span>
        <span><span className="mr-1 inline-block h-2 w-2 rounded-sm bg-loss" />Expenses</span>
      </p>
    </div>
  )
}

const PALETTE = ['#0f8a5f', '#c2410c', '#2563eb', '#a16207', '#7c3aed', '#0e7490', '#be185d', '#475569']

export function CategoryBars({ data }: { data: CategoryExpense[] }) {
  if (!data.length) return <Empty text="Not enough financial data to display this chart." />
  const total = data.reduce((s, d) => s + num(d.amount), 0) || 1
  const sorted = [...data].sort((a, b) => num(b.amount) - num(a.amount))
  return (
    <ul className="space-y-3">
      {sorted.map((d, i) => {
        const pct = (num(d.amount) / total) * 100
        return (
          <li key={d.category}>
            <div className="mb-1 flex justify-between text-sm"><span>{d.category}</span><span>{formatINR(d.amount)} · {pct.toFixed(0)}%</span></div>
            <div className="h-2 rounded-full bg-slate-100"><div className="h-2 rounded-full" style={{ width: `${pct}%`, background: PALETTE[i % PALETTE.length] }} /></div>
          </li>
        )
      })}
    </ul>
  )
}

export function BudgetProgress({ data }: { data: BudgetVsActual[] }) {
  if (!data.length) return <Empty text="No budgets for this month." />
  return (
    <ul className="space-y-4">
      {data.map((b) => {
        const pct = num(b.percentage_used), over = pct > 100
        return (
          <li key={b.category}>
            <div className="mb-1 flex flex-wrap justify-between gap-x-3 text-sm">
              <span className="font-medium">{b.category}</span>
              <span>{formatINR(b.spent)} / {formatINR(b.budget)}</span>
            </div>
            <div className="h-2.5 rounded-full bg-slate-100" role="progressbar" aria-valuenow={Math.round(pct)} aria-valuemin={0} aria-valuemax={100} aria-label={`${b.category} budget used`}>
              <div className={`h-2.5 rounded-full ${over ? 'bg-loss' : pct > 80 ? 'bg-amber-500' : 'bg-gain'}`} style={{ width: `${Math.min(pct, 100)}%` }} />
            </div>
            <p className={`mt-1 text-xs ${over ? 'font-medium text-loss' : 'text-slate-500'}`}>
              {formatPercent(pct)} used · {over ? `Over budget by ${formatINR(Math.abs(num(b.remaining)))}` : `${formatINR(b.remaining)} remaining`}
            </p>
          </li>
        )
      })}
    </ul>
  )
}

export function SavingsCard({ r }: { r: SavingsRate }) {
  const rate = num(r.savings_rate)
  return (
    <div>
      <p className={`text-4xl font-semibold ${rate >= 0 ? 'text-gain' : 'text-loss'}`}>{formatPercent(r.savings_rate)}</p>
      <p className="text-sm text-slate-500">of income saved</p>
      <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
        <div><dt className="text-slate-500">Income</dt><dd className="font-medium">{formatINR(r.total_income)}</dd></div>
        <div><dt className="text-slate-500">Expenses</dt><dd className="font-medium">{formatINR(r.total_expenses)}</dd></div>
        <div><dt className="text-slate-500">Savings</dt><dd className="font-medium">{formatINR(r.savings)}</dd></div>
      </dl>
    </div>
  )
}

export const RecentList = ({ items }: { items: Transaction[] }) => (
  <div className="overflow-x-auto">
    <table className="w-full text-left text-sm">
      <thead className="text-slate-500"><tr><th className="py-2 font-normal">Category</th><th className="font-normal">Type</th><th className="font-normal">Date</th><th className="text-right font-normal">Amount</th></tr></thead>
      <tbody>
        {items.map((t) => (
          <tr key={t.id} className="border-t border-slate-100">
            <td className="py-2.5">{t.category}</td><td><TypeBadge type={t.transaction_type} /></td>
            <td className="whitespace-nowrap">{formatDate(t.transaction_date)}</td><td className="text-right"><Amount t={t} /></td>
          </tr>
        ))}
      </tbody>
    </table>
  </div>
)
