from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import Budget, User
from app.schemas.budget import (
    BudgetCreate,
    BudgetResponse,
    BudgetUpdate,
)
from app.services.budget_service import (
    create_budget,
    delete_budget,
    get_user_budget,
    get_user_budgets,
    update_budget,
)

router = APIRouter(prefix="/api/budgets", tags=["Budgets"])

BUDGET_NOT_FOUND = "Budget not found"


@router.post(
    "/",
    response_model=BudgetResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_budget_endpoint(
    budget_data: BudgetCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Budget:
    return create_budget(db, budget_data, current_user)


@router.get("/", response_model=list[BudgetResponse])
def list_budgets_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[Budget]:
    return list(get_user_budgets(db, current_user))


@router.get("/{budget_id}", response_model=BudgetResponse)
def get_budget_endpoint(
        budget_id: Annotated[
            int,
            Path(
                ge=1,
                le=9223372036854775807,
            ),
        ],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Budget:
    budget = get_user_budget(db, budget_id, current_user)
    if budget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=BUDGET_NOT_FOUND,
        )
    return budget


@router.put("/{budget_id}", response_model=BudgetResponse)
def update_budget_endpoint(
        budget_id: Annotated[
            int,
            Path(
                ge=1,
                le=9223372036854775807,
            ),
        ],
    update_data: BudgetUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Budget:
    budget = update_budget(db, budget_id, update_data, current_user)
    if budget is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=BUDGET_NOT_FOUND,
        )
    return budget


@router.delete("/{budget_id}")
def delete_budget_endpoint(
        budget_id: Annotated[
            int,
            Path(
                ge=1,
                le=9223372036854775807,
            ),
        ],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    deleted = delete_budget(db, budget_id, current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=BUDGET_NOT_FOUND,
        )
    return {"message": "Budget deleted successfully"}