from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.database import get_db
from app.db.models import Transaction, User
from app.schemas.transaction import (
    TransactionCreate,
    TransactionResponse,
    TransactionUpdate,
)
from app.services.transaction_service import (
    create_transaction,
    delete_transaction,
    get_user_transaction,
    get_user_transactions,
    update_transaction,
)

router = APIRouter(prefix="/api/transactions", tags=["Transactions"])

TRANSACTION_NOT_FOUND = "Transaction not found"


@router.post(
    "/",
    response_model=TransactionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_transaction_endpoint(
    transaction_data: TransactionCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Transaction:
    return create_transaction(db, transaction_data, current_user)


@router.get("/", response_model=list[TransactionResponse])
def list_transactions_endpoint(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> list[Transaction]:
    return list(get_user_transactions(db, current_user))


@router.get("/{transaction_id}", response_model=TransactionResponse)
def get_transaction_endpoint(
    transaction_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Transaction:
    transaction = get_user_transaction(db, transaction_id, current_user)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )
    return transaction


@router.put("/{transaction_id}", response_model=TransactionResponse)
def update_transaction_endpoint(
    transaction_id: int,
    update_data: TransactionUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> Transaction:
    transaction = update_transaction(db, transaction_id, update_data, current_user)
    if transaction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )
    return transaction


@router.delete("/{transaction_id}")
def delete_transaction_endpoint(
    transaction_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict[str, str]:
    deleted = delete_transaction(db, transaction_id, current_user)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=TRANSACTION_NOT_FOUND,
        )
    return {"message": "Transaction deleted successfully"}



