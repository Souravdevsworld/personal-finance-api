from datetime import date, datetime
from decimal import Decimal
from typing import Literal
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


TransactionType = Literal["income", "expense"]
Category = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
    ),
]


class TransactionCreate(BaseModel):
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    transaction_type: TransactionType
    category: Category
    description: str | None = Field(default=None, max_length=500)
    transaction_date: date


class TransactionUpdate(BaseModel):
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    transaction_type: TransactionType | None = None
    category:Category | None = None
    description: str | None = Field(
        default=None,
        max_length=500,
    )
    transaction_date: date | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        non_nullable_fields = {
            "amount",
            "transaction_type",
            "category",
            "transaction_date",
        }

        for field in non_nullable_fields:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class TransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    amount: Decimal
    transaction_type: TransactionType
    category: str
    description: str | None
    transaction_date: date
    created_at: datetime