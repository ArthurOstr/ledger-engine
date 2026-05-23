import enum
from decimal import Decimal
from typing import Optional
from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Numeric, DateTime, func, ForeignKey, Integer, Enum

from app.database import Base

class BankSource(str, enum.Enum):
    MONOBANK = "monobank"
    PRIVATBANK = "privatbank"

class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True
    )
    bank: Mapped[BankSource] = mapped_column(Enum(BankSource), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    card: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    currency: Mapped[str] = mapped_column(String(3))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    transaction_currency: Mapped[str] = mapped_column(String(3))
    transaction_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    date: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    balance_currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    hash_id: Mapped[str] = mapped_column(String, unique=True, index=True)

    # Monobank extensions
    mcc: Mapped[Optional[str]] = mapped_column(Integer, nullable=True)
    commissions: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    cashback: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 2), nullable=True)
    exchange_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 4), nullable=True)

    owner = relationship("User", back_populates="transactions")
