from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.transaction import Transaction


async def fetch_transaction(
    db: AsyncSession, user_id: int, limit: int = 50, offset: int = 0
) -> Sequence[Transaction]:
    """
    Asynchronously queries the database for transactions,
    ordering the by the most recent date first.
    """
    stmt = (
        select(Transaction)
        .where(Transaction.owner_id == user_id)
        .order_by(Transaction.date.desc())
        .limit(limit)
        .offset(offset)
    )

    result = await db.execute(stmt)
    return result.scalars().all()
