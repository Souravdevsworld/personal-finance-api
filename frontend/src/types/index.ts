// Shapes follow the prompt's contract. Verify against /openapi.json.
// Pydantic v2 serialises Decimal as a string, so amounts may arrive as string | number.
export type Money = number | string
export type TransactionType = 'income' | 'expense'

export interface User { id: number; email: string; created_at: string }
export interface Token { access_token: string; token_type: string }

export interface Transaction {
  id: number; user_id: number; amount: Money; transaction_type: TransactionType
  category: string; description: string | null; transaction_date: string; created_at: string
}
export interface TransactionInput {
  amount: string; transaction_type: TransactionType; category: string
  description?: string | null; transaction_date: string
}

export interface Budget { id: number; user_id: number; category: string; amount: Money; month: string; created_at: string }
export interface BudgetInput { category: string; amount: string; month: string }

export interface Summary { total_income: Money; total_expenses: Money; balance: Money; transaction_count: number }
export interface CategoryExpense { category: string; amount: Money }
export interface MonthlyTrend { month: string; income: Money; expenses: Money }
export interface BudgetVsActual { category: string; budget: Money; spent: Money; remaining: Money; percentage_used: Money }
export interface SavingsRate { total_income: Money; total_expenses: Money; savings: Money; savings_rate: Money }
