from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Month = Annotated[
    str,
    StringConstraints(
        pattern=r"^(19|20)[0-9]{2}-(0[1-9]|1[0-2])$"
    ),
]

Category = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=100,
    ),
]


class BudgetCreate(BaseModel):
    category: Category
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    month: Month

class BudgetUpdate(BaseModel):
    category: Category | None = None
    amount: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=12,
        decimal_places=2,
    )
    month: Month | None = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self):
        non_nullable_fields = {
            "category",
            "amount",
            "month",
        }

        for field in non_nullable_fields:
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")

        return self


class BudgetResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    category: str
    amount: Decimal
    month: str
    created_at: datetime
