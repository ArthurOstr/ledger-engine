import os
import logging
from arq.connections import RedisSettings
from sqlalchemy.future import select

from app.services.ledger_parser import parse_excel_payload, save_transactions_to_db
from app.database import AsyncSessionLocal
from app.models.category_rule import CategoryRule

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("worker")


async def process_excel_file(ctx, file_bytes: bytes, user_id: int):
    logger.info(
        f"Picked up job for User ID: {user_id}. File size: {len(file_bytes)} bytes."
    )

    try:
        async with AsyncSessionLocal() as db_session:

            # Download the specific user's rules from PostgreSQL
            stmt = select(CategoryRule).where(
                CategoryRule.owner_id == user_id,
                CategoryRule.is_active == True,
            )

            result = await db_session.execute(stmt)
            rules_object = result.scalars().all()

            # Convert db object into Python dict
            user_rules = {rule.keyword: rule.assigned_category for rule in rules_object}

            # Raw files and the custom rules are going to Pandas parser
            transactions = parse_excel_payload(
                contents=file_bytes,
                user_id=user_id,
                user_rules=user_rules
            )

        # Saving to the database
        inserted_count = await save_transactions_to_db(
                db=db_session, transactions=transactions, user_id=user_id
        )

        logger.info(f"Successfully extracted {inserted_count} rows.")
        return f"Processed {inserted_count} transactions."

    except Exception as e:
        logger.exception(f"Fatal error processing file: {str(e)}")
        raise e


class WorkerSettings:
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://localhost:6379/0")
    )
    functions = [process_excel_file]
