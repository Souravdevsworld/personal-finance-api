import { request } from './client'
import type {
  Budget, BudgetInput, BudgetVsActual, CategoryExpense, MonthlyTrend, SavingsRate,
  Summary, Token, Transaction, TransactionInput, User,
} from '../types'

export const authApi = {
  register: (email: string, password: string) => request<User>('/api/auth/register', { method: 'POST', body: { email, password }, auth: false }),
  // OAuth2 password flow: form-encoded, email goes in "username"
  login: (email: string, password: string) =>
    request<Token>('/api/auth/login', { method: 'POST', form: new URLSearchParams({ username: email, password }), auth: false }),
}

export const transactionsApi = {
  list: () => request<Transaction[]>('/api/transactions/'),
  get: (id: number) => request<Transaction>(`/api/transactions/${id}`),
  create: (b: TransactionInput) => request<Transaction>('/api/transactions/', { method: 'POST', body: b }),
  update: (id: number, b: TransactionInput) => request<Transaction>(`/api/transactions/${id}`, { method: 'PUT', body: b }),
  remove: (id: number) => request<void>(`/api/transactions/${id}`, { method: 'DELETE' }),
}

export const budgetsApi = {
  list: () => request<Budget[]>('/api/budgets/'),
  get: (id: number) => request<Budget>(`/api/budgets/${id}`),
  create: (b: BudgetInput) => request<Budget>('/api/budgets/', { method: 'POST', body: b }),
  update: (id: number, b: BudgetInput) => request<Budget>(`/api/budgets/${id}`, { method: 'PUT', body: b }),
  remove: (id: number) => request<void>(`/api/budgets/${id}`, { method: 'DELETE' }),
}

export const analyticsApi = {
  summary: (month?: string) => request<Summary>('/api/analytics/summary', { query: { month } }),
  categories: (month?: string) => request<CategoryExpense[]>('/api/analytics/categories', { query: { month } }),
  trend: (months: number) => request<MonthlyTrend[]>('/api/analytics/trend', { query: { months } }),
  budgetVsActual: (month: string) => request<BudgetVsActual[]>('/api/analytics/budget-vs-actual', { query: { month } }),
  savingsRate: (month?: string) => request<SavingsRate>('/api/analytics/savings-rate', { query: { month } }),
}
