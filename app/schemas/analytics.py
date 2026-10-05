from decimal import Decimal

from pydantic import BaseModel


class FinancialSummaryResponse(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    balance: Decimal
    transaction_count: int


class CategoryExpenseResponse(BaseModel):
    category: str
    amount: Decimal


class MonthlyTrendResponse(BaseModel):
    month: str
    income: Decimal
    expenses: Decimal


class BudgetVsActualResponse(BaseModel):
    category: str
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    percentage_used: Decimal


class SavingsRateResponse(BaseModel):
    total_income: Decimal
    total_expenses: Decimal
    savings: Decimal
    savings_rate: Decimal


