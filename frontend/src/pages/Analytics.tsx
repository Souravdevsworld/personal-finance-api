import { useState } from 'react'
import { analyticsApi } from '../api'
import { PageHeader } from '../components/Layout'
import { Async, Card, Skeleton } from '../components/ui'
import { BudgetProgress, CategoryBars, SavingsCard, SummaryCards, TrendChart } from '../components/widgets'
import { useApi } from '../hooks/useApi'
import { currentMonth } from '../utils/format'

export default function Analytics() {
  const [months, setMonths] = useState(6)
  const [month, setMonth] = useState(currentMonth())
  const [period, setPeriod] = useState('') // empty = all time
  const summary = useApi(() => analyticsApi.summary(period || undefined), [period])
  const trend = useApi(() => analyticsApi.trend(months), [months])
  const cats = useApi(() => analyticsApi.categories(period || undefined), [period])
  const bva = useApi(() => analyticsApi.budgetVsActual(month), [month])
  const rate = useApi(() => analyticsApi.savingsRate(period || undefined), [period])
  const sk = <Skeleton className="h-48" />
  const monthInput = (v: string, set: (s: string) => void, label: string) => <input aria-label={label} type="month" className="input w-auto" value={v} onChange={(e) => set(e.target.value)} />

  return (
    <>
      <PageHeader title="Analytics" action={<span className="flex items-center gap-2">{monthInput(period, setPeriod, 'Period month')}{period ? <button className="text-sm underline" onClick={() => setPeriod('')}>All time</button> : <span className="text-sm text-slate-500">All time</span>}</span>} />
      <div className="space-y-4">
        <Card title="Income vs expenses"><Async state={summary} skeleton={<Skeleton className="h-24" />}>{(s) => <SummaryCards s={s} rate={rate.data} />}</Async></Card>
        <Card title="Monthly trend" action={
          <select aria-label="Number of months" className="input w-auto" value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            {[3, 6, 12].map((m) => <option key={m} value={m}>{m} months</option>)}
          </select>}>
          <Async state={trend} skeleton={sk}>{(d) => <TrendChart data={d} />}</Async>
        </Card>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Spending by category"><Async state={cats} skeleton={sk}>{(d) => <CategoryBars data={d} />}</Async></Card>
          <Card title="Savings rate">
            <Async state={rate} skeleton={sk}>{(r) => <SavingsCard r={r} />}</Async>
          </Card>
        </div>
        <Card title="Budget vs actual" action={monthInput(month, (v) => v && setMonth(v), 'Budget month')}><Async state={bva} skeleton={sk}>{(d) => <BudgetProgress data={d} />}</Async></Card>
      </div>
    </>
  )
}
