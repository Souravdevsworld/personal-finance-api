import { Link } from 'react-router-dom'
import { analyticsApi, transactionsApi } from '../api'
import { PageHeader } from '../components/Layout'
import { Async, Card, Empty, Skeleton } from '../components/ui'
import { BudgetProgress, CategoryBars, RecentList, SavingsCard, SummaryCards, TrendChart } from '../components/widgets'
import { useApi } from '../hooks/useApi'
import { currentMonth } from '../utils/format'

export default function Dashboard() {
  const summary = useApi(analyticsApi.summary, [])
  const rate = useApi(() => analyticsApi.savingsRate(), [])
  const trend = useApi(() => analyticsApi.trend(6), [])
  const cats = useApi(analyticsApi.categories, [])
  const bva = useApi(() => analyticsApi.budgetVsActual(currentMonth()), [])
  const txs = useApi(transactionsApi.list, [])
  const sk = <Skeleton className="h-48" />

  return (
    <>
      <PageHeader title="Financial overview" />
      <div className="space-y-4">
        <Async state={summary} skeleton={<Skeleton className="h-24" />}>{(s) => <SummaryCards s={s} rate={rate.data} />}</Async>
        <div className="grid gap-4 lg:grid-cols-5">
          <Card title="Income vs expenses (6 months)" className="lg:col-span-3"><Async state={trend} skeleton={sk}>{(d) => <TrendChart data={d} />}</Async></Card>
          <Card title="Savings rate" className="lg:col-span-2"><Async state={rate} skeleton={sk}>{(r) => <SavingsCard r={r} />}</Async></Card>
        </div>
        <div className="grid gap-4 lg:grid-cols-2">
          <Card title="Spending by category"><Async state={cats} skeleton={sk}>{(d) => <CategoryBars data={d} />}</Async></Card>
          <Card title="Budget progress this month"><Async state={bva} skeleton={sk}>{(d) => <BudgetProgress data={d} />}</Async></Card>
        </div>
        <Card title="Recent transactions" action={<Link to="/transactions" className="text-sm underline">View all transactions</Link>}>
          <Async state={txs} skeleton={sk}
            empty={(d) => d.length ? null : <Empty text="You don't have any transactions yet." action={<Link to="/transactions" className="btn-primary">Add transaction</Link>} />}>
            {(d) => <RecentList items={[...d].sort((a, b) => b.transaction_date.localeCompare(a.transaction_date)).slice(0, 5)} />}
          </Async>
        </Card>
      </div>
    </>
  )
}
