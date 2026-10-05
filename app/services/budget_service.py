from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Budget, User
from app.schemas.budget import BudgetCreate, BudgetUpdate


def create_budget(
    db: Session,
    budget_data: BudgetCreate,
    current_user: User,
) -> Budget:
    budget = Budget(
        **budget_data.model_dump(),
        user_id=current_user.id,
    )
    db.add(budget)
    db.commit()
    db.refresh(budget)
    return budget


def get_user_budgets(
    db: Session,
    current_user: User,
) -> Sequence[Budget]:
    statement = (
        select(Budget)
        .where(Budget.user_id == current_user.id)
        .order_by(Budget.month.desc(), Budget.id.desc())
    )
    return db.execute(statement).scalars().all()


def get_user_budget(
    db: Session,
    budget_id: int,
    current_user: User,
) -> Budget | None:
    statement = select(Budget).where(
        Budget.id == budget_id,
        Budget.user_id == current_user.id,
    )
    return db.execute(statement).scalar_one_or_none()


def update_budget(
    db: Session,
    budget_id: int,
    update_data: BudgetUpdate,
    current_user: User,
) -> Budget | None:
    budget = get_user_budget(db, budget_id, current_user)
    if budget is None:
        return None

    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(budget, field, value)

    db.commit()
    db.refresh(budget)
    return budget


def delete_budget(
    db: Session,
    budget_id: int,
    current_user: User,
) -> bool:
    budget = get_user_budget(db, budget_id, current_user)
    if budget is None:
        return False

    db.delete(budget)
    db.commit()
    return True