from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional


class TransactionBase(BaseModel):
    date: datetime
    category: Optional[str] = None
    card: Optional[str] = None
    description: Optional[str] = None
    amount: Decimal = Field(..., max_digits=10, decimal_places=2)
    currency: str = Field(..., min_length=3, max_length=3)
    balance_after: Decimal = Field(..., max_digits=10, decimal_places=2)
    balance_currency: str = Field(..., min_length=3, max_length=3)
    transaction_currency: str = Field(..., min_length=3, max_length=3)
    transaction_amount: Decimal = Field(..., max_digits=10, decimal_places=2)


class TransactionCreate(TransactionBase):
    """Schema for validating incoming data before database insertion."""

    pass


class ORMResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TransactionResponse(TransactionBase, ORMResponseBase):
    """Schema for validating outgoing data returned to the client."""

    id: int
    created_at: datetime
