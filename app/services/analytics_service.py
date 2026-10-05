from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import TypedDict

from sqlalchemy import Select, case, func, select
from sqlalchemy.orm import Session

from app.db.models import Budget, Transaction, User

TWO_PLACES = Decimal("0.01")
ZERO = Decimal("0.00")
ONE_HUNDRED = Decimal("100")

MIN_TREND_MONTHS = 1
MAX_TREND_MONTHS = 12


class FinancialSummary(TypedDict):
    total_income: Decimal
    total_expenses: Decimal
    balance: Decimal
    transaction_count: int


class CategoryExpense(TypedDict):
    category: str
    amount: Decimal


class MonthlyTrendItem(TypedDict):
    month: str
    income: Decimal
    expenses: Decimal


class BudgetVsActualItem(TypedDict):
    category: str
    budget: Decimal
    spent: Decimal
    remaining: Decimal
    percentage_used: Decimal


class SavingsRate(TypedDict):
    total_income: Decimal
    total_expenses: Decimal
    savings: Decimal
    savings_rate: Decimal


def _to_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if not isinstance(value, Decimal):
        value = Decimal(str(value))
    return value.quantize(TWO_PLACES)


def _month_bounds(month: str) -> tuple[date, date]:
    """Return the first day of the month and the first day of the next month."""
    try:
        year_str, month_str = month.split("-")
        if len(year_str) != 4 or len(month_str) != 2:
            raise ValueError
        year = int(year_str)
        month_number = int(month_str)
        start = date(year, month_number, 1)
    except ValueError:
        raise ValueError("Month must be in YYYY-MM format") from None

    if month_number == 12:
        end = date(year + 1, 1, 1)
    else:
        end = date(year, month_number + 1, 1)
    return start, end


def _apply_month_filter(statement: Select, month: str | None) -> Select:
    if month is None:
        return statement
    start, end = _month_bounds(month)
    return statement.where(
        Transaction.transaction_date >= start,
        Transaction.transaction_date < end,
    )


def _add_months(year: int, month: int, delta: int) -> tuple[int, int]:
    """Shift a (year, month) pair by delta months (delta may be negative)."""
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal:
    """Return (numerator / denominator) * 100, or 0.00 if denominator is zero."""
    if denominator == 0:
        return ZERO
    return (numerator / denominator * ONE_HUNDRED).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )


def get_financial_summary(
    db: Session,
    current_user: User,
    month: str | None = None,
) -> FinancialSummary:
    statement = select(
        func.sum(
            case(
                (Transaction.transaction_type == "income", Transaction.amount),
                else_=None,
            )
        ).label("total_income"),
        func.sum(
            case(
                (Transaction.transaction_type == "expense", Transaction.amount),
                else_=None,
            )
        ).label("total_expenses"),
        func.count(Transaction.id).label("transaction_count"),
    ).where(Transaction.user_id == current_user.id)

    statement = _apply_month_filter(statement, month)

    row = db.execute(statement).one()

    total_income = _to_decimal(row.total_income)
    total_expenses = _to_decimal(row.total_expenses)

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "balance": total_income - total_expenses,
        "transaction_count": int(row.transaction_count or 0),
    }


def get_category_expenses(
    db: Session,
    current_user: User,
    month: str | None = None,
) -> list[CategoryExpense]:
    total = func.sum(Transaction.amount).label("total")

    statement = (
        select(Transaction.category, total)
        .where(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == "expense",
        )
        .group_by(Transaction.category)
        .order_by(total.desc(), Transaction.category.asc())
    )

    statement = _apply_month_filter(statement, month)

    rows = db.execute(statement).all()

    return [
        {"category": row.category, "amount": _to_decimal(row.total)}
        for row in rows
    ]


def get_monthly_trend(
    db: Session,
    current_user: User,
    months: int = 6,
) -> list[MonthlyTrendItem]:
    if not MIN_TREND_MONTHS <= months <= MAX_TREND_MONTHS:
        raise ValueError(
            f"months must be between {MIN_TREND_MONTHS} and {MAX_TREND_MONTHS}"
        )

    today = datetime.now(timezone.utc).date()

    # Build the ordered list of (year, month) buckets ending at the current month.
    buckets: list[tuple[int, int]] = [
        _add_months(today.year, today.month, -offset)
        for offset in range(months - 1, -1, -1)
    ]

    first_year, first_month = buckets[0]
    last_year, last_month = buckets[-1]
    range_start = date(first_year, first_month, 1)
    next_year, next_month = _add_months(last_year, last_month, 1)
    range_end = date(next_year, next_month, 1)

    year_col = func.extract("year", Transaction.transaction_date).label("year")
    month_col = func.extract("month", Transaction.transaction_date).label("month")

    statement = (
        select(
            year_col,
            month_col,
            func.sum(
                case(
                    (Transaction.transaction_type == "income", Transaction.amount),
                    else_=None,
                )
            ).label("income"),
            func.sum(
                case(
                    (Transaction.transaction_type == "expense", Transaction.amount),
                    else_=None,
                )
            ).label("expenses"),
        )
        .where(
            Transaction.user_id == current_user.id,
            Transaction.transaction_date >= range_start,
            Transaction.transaction_date < range_end,
        )
        .group_by(year_col, month_col)
    )

    totals: dict[tuple[int, int], tuple[Decimal, Decimal]] = {}
    for row in db.execute(statement).all():
        key = (int(row.year), int(row.month))
        totals[key] = (_to_decimal(row.income), _to_decimal(row.expenses))

    trend: list[MonthlyTrendItem] = []
    for year, month_number in buckets:
        income, expenses = totals.get((year, month_number), (ZERO, ZERO))
        trend.append(
            {
                "month": f"{year:04d}-{month_number:02d}",
                "income": income,
                "expenses": expenses,
            }
        )
    return trend


def get_budget_vs_actual(
    db: Session,
    current_user: User,
    month: str,
) -> list[BudgetVsActualItem]:
    start, end = _month_bounds(month)  # Raises ValueError on invalid format.

    budgets = (
        db.execute(
            select(Budget)
            .where(
                Budget.user_id == current_user.id,
                Budget.month == month,
            )
            .order_by(Budget.category.asc())
        )
        .scalars()
        .all()
    )

    if not budgets:
        return []

    categories = [budget.category for budget in budgets]

    spent_statement = (
        select(
            Transaction.category,
            func.sum(Transaction.amount).label("spent"),
        )
        .where(
            Transaction.user_id == current_user.id,
            Transaction.transaction_type == "expense",
            Transaction.transaction_date >= start,
            Transaction.transaction_date < end,
            Transaction.category.in_(categories),
        )
        .group_by(Transaction.category)
    )

    spent_by_category: dict[str, Decimal] = {
        row.category: _to_decimal(row.spent)
        for row in db.execute(spent_statement).all()
    }

    results: list[BudgetVsActualItem] = []
    for budget in budgets:
        budget_amount = _to_decimal(budget.amount)
        spent = spent_by_category.get(budget.category, ZERO)
        results.append(
            {
                "category": budget.category,
                "budget": budget_amount,
                "spent": spent,
                "remaining": budget_amount - spent,
                "percentage_used": _percentage(spent, budget_amount),
            }
        )
    return results


def get_savings_rate(
    db: Session,
    current_user: User,
    month: str | None = None,
) -> SavingsRate:
    summary = get_financial_summary(db, current_user, month)

    total_income = summary["total_income"]
    total_expenses = summary["total_expenses"]
    savings = total_income - total_expenses

    return {
        "total_income": total_income,
        "total_expenses": total_expenses,
        "savings": savings,
        "savings_rate": _percentage(savings, total_income),
    }