from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import User
from app.schemas.analytics import (
    BudgetVsActualResponse,
    CategoryExpenseResponse,
    FinancialSummaryResponse,
    MonthlyTrendResponse,
    SavingsRateResponse,
)
from app.services.analytics_service import (
    get_budget_vs_actual,
    get_category_expenses,
    get_financial_summary,
    get_monthly_trend,
    get_savings_rate,
)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"

MonthQuery = Annotated[
    str | None,
    Query(
        pattern=MONTH_PATTERN,
        description="Month in YYYY-MM format",
        examples=["2026-10"],
    ),
]

RequiredMonthQuery = Annotated[
    str,
    Query(
        pattern=MONTH_PATTERN,
        description="Month in YYYY-MM format",
        examples=["2026-10"],
    ),
]

MonthsQuery = Annotated[
    int,
    Query(
        ge=1,
        le=12,
        description="Number of months to include, ending with the current month",
    ),
]


@router.get("/summary", response_model=FinancialSummaryResponse)
def get_summary_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: MonthQuery = None,
) -> FinancialSummaryResponse:
    summary = get_financial_summary(db, current_user, month)
    return FinancialSummaryResponse(**summary)


@router.get("/categories", response_model=list[CategoryExpenseResponse])
def get_categories_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: MonthQuery = None,
) -> list[CategoryExpenseResponse]:
    expenses = get_category_expenses(db, current_user, month)
    return [CategoryExpenseResponse(**expense) for expense in expenses]


@router.get("/trend", response_model=list[MonthlyTrendResponse])
def get_trend_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    months: MonthsQuery = 6,
) -> list[MonthlyTrendResponse]:
    trend = get_monthly_trend(db, current_user, months)
    return [MonthlyTrendResponse(**item) for item in trend]


@router.get("/budget-vs-actual", response_model=list[BudgetVsActualResponse])
def get_budget_vs_actual_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: RequiredMonthQuery,
) -> list[BudgetVsActualResponse]:
    results = get_budget_vs_actual(db, current_user, month)
    return [BudgetVsActualResponse(**item) for item in results]


@router.get("/savings-rate", response_model=SavingsRateResponse)
def get_savings_rate_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    month: MonthQuery = None,
) -> SavingsRateResponse:
    result = get_savings_rate(db, current_user, month)
    return SavingsRateResponse(**result)





