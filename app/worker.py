import logging
from functools import wraps
from typing import Any
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, text
from fastapi import HTTPException

from app.services.parsers.registry import parse_excel_payload
from app.services.ledger_parser import save_transactions_to_db
from app.database import AsyncSessionLocal
from app.models.category_rule import CategoryRule
from app.models.user import User
from app.core.config import settings
from app.services.storage import storage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worker")

def with_db_session(func):
    """
   Reusable security and lifecycle wrapper for background tasks.
   The main purpose of this decorator is to isolate connection with prod adn test database.
    """
    @wraps(func)
    async def wrapper(ctx, *args, **kwargs):
        db_session = ctx.get("db_session")
        is_test_session = db_session is not None

        if is_test_session:
            return await func(ctx, db_session, *args, **kwargs)

        async with AsyncSessionLocal() as fresh_session:
            try:
                return await func(ctx, fresh_session, *args, **kwargs)
            finally:
                await fresh_session.close()
    return wrapper

@with_db_session
async def process_excel_file(
        ctx: dict[str, Any],
        db_session: AsyncSession,
        file_path: str,
        user_id: int
) -> dict[str, Any]:

    job_id = ctx.get("job_id", "unknown")

    logger.info(
        f"Picked up job [{job_id}] for User ID: {user_id}. File path: {file_path}."
    )

    try:
        try:
            file_bytes = storage.get(file_path)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="File path does not exist in storage."
            )


        # KERNEL KEY INJECTION.
        # Set the PostgreSQL session variable so RLS allows worker to see the user's data
        await db_session.execute(
            text(f"SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": str(int(user_id))},
        )

        # Download the specific user's regex rules from PostgreSQL
        stmt = select(CategoryRule).where(
            CategoryRule.owner_id == user_id,
            CategoryRule.is_active.is_(True),
        )

        result = await db_session.execute(stmt)
        rules_object = result.scalars().all()

        # Convert db object into Python dict
        user_rules = {rule.keyword: rule.assigned_category for rule in rules_object}

        # Raw files and the custom rules are going to Pandas parsers
        transactions = parse_excel_payload(
            contents=file_bytes, user_id=user_id, user_rules=user_rules
        )
        parsed_count = len(transactions)

        # Saving to the database
        inserted_count = await save_transactions_to_db(
            db=db_session, transactions=transactions, user_id=user_id
        )
        duplicate_count = parsed_count - inserted_count

        logger.info(f"Job [{job_id}] parsed {parsed_count} rows:"
                    f" successfully extracted {inserted_count} rows, {duplicate_count} duplicate rows.")
        return {
            "status": "SUCCESS",
            "inserted_count": inserted_count,
            "error": None
        }

    except HTTPException as http_exc:
        logger.warning(f"Validation error in job [{job_id}] with error: {str(http_exc)}")
        await db_session.rollback()

        return {
            "status": "FAILED",
            "inserted_count": 0,
            "error": http_exc.detail
        }
    except Exception as e:
        logger.exception(f"Unexpected fatal error processing job [{job_id}]: {str(e)}")
        await db_session.rollback()
        return {
            "status": "FAILED",
            "inserted_count": 0,
            "error": "Internal server error occurred while processing statement.",
        }
    finally:
        await storage.delete(file_path)

class WorkerSettings:
    redis_settings = settings.redis_settings
    functions = [process_excel_file]
    poll_delay = 10.0
