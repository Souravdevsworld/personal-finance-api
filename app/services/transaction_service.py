from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Transaction, User
from app.schemas.transaction import TransactionCreate, TransactionUpdate


def create_transaction(
    db: Session,
    transaction_data: TransactionCreate,
    current_user: User,
) -> Transaction:
    transaction = Transaction(
        **transaction_data.model_dump(),
        user_id=current_user.id,
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def get_user_transactions(
    db: Session,
    current_user: User,
) -> Sequence[Transaction]:
    statement = (
        select(Transaction)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.transaction_date.desc(), Transaction.id.desc())
    )
    return db.execute(statement).scalars().all()


def get_user_transaction(
    db: Session,
    transaction_id: int,
    current_user: User,
) -> Transaction | None:
    statement = select(Transaction).where(
        Transaction.id == transaction_id,
        Transaction.user_id == current_user.id,
    )
    return db.execute(statement).scalar_one_or_none()


def update_transaction(
    db: Session,
    transaction_id: int,
    update_data: TransactionUpdate,
    current_user: User,
) -> Transaction | None:
    transaction = get_user_transaction(db, transaction_id, current_user)
    if transaction is None:
        return None

    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(transaction, field, value)

    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(
    db: Session,
    transaction_id: int,
    current_user: User,
) -> bool:
    transaction = get_user_transaction(db, transaction_id, current_user)
    if transaction is None:
        return False

    db.delete(transaction)
    db.commit()
    return True