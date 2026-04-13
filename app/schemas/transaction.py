from datetime import datetime
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field


class TransactionBase(BaseModel):
    date: datetime
    amount: Decimal = Field(
        ...,
        description="Transaction amount. Positive for income, negative for expense.",
    )
    # category: str | None = None


class TransactionCreate(TransactionBase):
    """Schema for validating incoming data before database insertion."""

    pass


class ORMResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TransactionResponse(TransactionBase, ORMResponseBase):
    """Schema for validating outgoing data returned to the client."""

    id: int
