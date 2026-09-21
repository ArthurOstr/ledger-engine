from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from itertools import batched

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionCreate
from app.services.parsers.registry import detect_bank_source,parse_excel_payload
from app.services.parsers.base import generate_row_hash, sanitize_data

__all__ = [
    "detect_bank_source",
    "parse_excel_payload",
    "generate_row_hash",
    "sanitize_data",
    "save_transactions_to_db",
]

async def save_transactions_to_db(
    db: AsyncSession,
        transactions: list[TransactionCreate],
        user_id: int,
        chunk_size: int = 1000
) -> int:
    # Pydantic models to dictionaries
    values_to_insert = []
    for record in transactions:
        record_dict = record.model_dump()
        record_dict["owner_id"] = user_id
        values_to_insert.append(record_dict)

    if not values_to_insert:
        return 0

    total_inserted = 0

    for chunk in batched(values_to_insert, chunk_size):
        # Special postgresql Insert statement
        stmt = (
            insert(Transaction)
            .values(list(chunk))
            .on_conflict_do_nothing(index_elements=["hash_id"])
        )

        result = await db.execute(stmt)
        total_inserted += result.rowcount

    await db.commit()

    return total_inserted
