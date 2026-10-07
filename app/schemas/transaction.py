from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from decimal import Decimal
from typing import Optional, Literal

from app.models.transaction import BankSource

# TRANSACTION DOMAIN SCHEMAS

class TransactionBase(BaseModel):
    date: datetime
    bank: BankSource
    category: Optional[str] = None
    card: Optional[str] = None
    description: Optional[str] = None
    amount: Decimal = Field(..., max_digits=10, decimal_places=2)
    currency: str = Field(..., min_length=3, max_length=3)
    balance_after: Decimal = Field(..., max_digits=10, decimal_places=2)
    balance_currency: str = Field(..., min_length=3, max_length=3)
    transaction_currency: str = Field(..., min_length=3, max_length=3)
    transaction_amount: Decimal = Field(..., max_digits=10, decimal_places=2)
    hash_id: str

    mcc: Optional[int] = None
    commissions: Optional[Decimal] = None
    cashback: Optional[Decimal] = None
    exchange_rate: Optional[Decimal] = None

class TransactionCreate(TransactionBase):
    """Schema for validating incoming data before database insertion."""

    pass


class ORMResponseBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TransactionResponse(TransactionBase, ORMResponseBase):
    """Schema for validating outgoing data returned to the client."""

    id: int
    created_at: datetime

# JOB STATUS SCHEMAS

class UploadResponse(BaseModel):
    """Response returned immediately upon staging a file (HTTP 202)."""
    filename: Optional[str] = None
    user_email: Optional[str] = None
    message: str
    job_id: str
    status: Literal["queued"] = "queued"


class JobExecutionResult(BaseModel):
    """Inner payload emitted by the arq worker upon completion."""
    status: Literal["SUCCESS", "FAILED"]
    inserted_count: int = 0
    error: Optional[str] = None


class StatusResponseSchema(BaseModel):
    """
    Response returned by GET /transactions/status/{job_id}.
    Matches the StatusResponse interface on the frontend.
    """
    job_id: str
    status: Literal["queued", "in_progress", "completed", "failed"]
    inserted_count: Optional[int] = None
    error: Optional[str] = None

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "job_id": "35185a65cb3f4cd6939ba200bc07fff7",
                "status": "completed",
                "inserted_count": 42,
                "error": None,
            }
        }
    )