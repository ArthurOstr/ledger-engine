import os
import logging
from arq.connections import RedisSettings

from app.services.ledger_parser import parse_excel_payload, save_transactions_to_db
from app.database import AsyncSessionLocal

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
        transactions = parse_excel_payload(contents=file_bytes, user_id=user_id)

        # Link to database
        async with AsyncSessionLocal() as db_session:
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
