import os
import logging
from sqlalchemy import text
from functools import wraps
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.services.ledger_parser import parse_excel_payload, save_transactions_to_db
from app.database import AsyncSessionLocal
from app.models.category_rule import CategoryRule
from app.models.user import User
from app.models.transaction import Transaction
from app.core.config import settings

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
async def process_excel_file(ctx, db_session: AsyncSession, file_bytes: bytes, user_id: int):

    job_id = ctx.get("job_id")
    logger.info(
        f"Picked up job [{job_id}] for User ID: {user_id}. File size: {len(file_bytes)} bytes."
    )

    try:
        # KERNEL KEY INJECTION
        # Set the PostgreSQL session variable so RLS allows worker to see the user's data
        safe_user_id = str(int(user_id))
        await db_session.execute(
            text(f"SELECT set_config('app.current_user_id', '{safe_user_id}', true)")
        )

        # Download the specific user's rules from PostgreSQL
        stmt = select(CategoryRule).where(
            CategoryRule.owner_id == user_id,
            CategoryRule.is_active,
        )

        result = await db_session.execute(stmt)
        rules_object = result.scalars().all()

        # Convert db object into Python dict
        user_rules = {rule.keyword: rule.assigned_category for rule in rules_object}

        # Raw files and the custom rules are going to Pandas parser
        transactions = parse_excel_payload(
            contents=file_bytes, user_id=user_id, user_rules=user_rules
        )

        # Saving to the database
        inserted_count = await save_transactions_to_db(
            db=db_session, transactions=transactions, user_id=user_id
        )

        await db_session.commit()
        logger.info(f"Successfully extracted {inserted_count} rows.")
        return {
            "status": "SUCCESS",
            "inserted_count": inserted_count,
            "error": None
        }

    except Exception as e:
        logger.exception(f"Fatal error processing file: {str(e)}")

        await db_session.rollback()

        return {
            "status": "FAILED",
            "inserted_count": 0,
            "error": str(e)
        }


class WorkerSettings:
    redis_settings = settings.redis_settings
    functions = [process_excel_file]
    poll_delay = 10.0
