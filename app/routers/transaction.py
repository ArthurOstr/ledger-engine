import os
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from arq import create_pool
from arq.jobs import Job, JobStatus
from arq.connections import RedisSettings

from app.database import get_db
from app.services.ledger_queries import fetch_transaction
from app.schemas.transaction import TransactionResponse
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


async def get_redis_pool():
    redis_settings = RedisSettings.from_dsn(
        os.getenv("REDIS_URL", "redis://redis:6379/0")
    )
    return await create_pool(redis_settings)


@router.post("/upload", status_code=202)
async def upload_ledger(
    file: UploadFile = File(...),
    redis_pool=Depends(get_redis_pool),
    current_user: User = Depends(get_current_user),
):
    # Shield from non-Excel files
    if not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(
            status_code=400, detail="Invalid file type. Only .xls or .xlsx allowed"
        )

    try:
        contents = await file.read()

        # Drop payload into the Redis Broker. It must match redis config(currently worker.py)
        job = await redis_pool.enqueue_job(
            "process_excel_file", contents, current_user.id
        )

        return {
            "filename": file.filename,
            "user_email": current_user.email,
            "message": "File successfully passed to the broker.",
            "job_id": job.job_id,
            "status": "queued",
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Broker rejection: {str(e)}")


@router.get("", response_model=list[TransactionResponse])
async def get_transaction(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Extracts the standardized financial data to populate the frontend dashboard.
    """
    records = await fetch_transaction(
        db=db, user_id=current_user.id, limit=limit, offset=offset
    )

    return records


@router.get("/status/{job_id}")
async def get_upload_status(job_id: str, redis_pool=Depends(get_redis_pool)):
    # Look up the specific job in the Redis RAM
    job = Job(job_id, redis_pool)

    status = await job.status()
    if status == JobStatus.not_found:
        return {"job_id": job_id, "status": "FAILED", "error": "Job expired or not found in Redis"}

    if status != JobStatus.complete:
        return {"job_id": job_id, "status": status.value.upper()}

    try:
        result_dict = await job.result(timeout=0)

        # Merge the worker's dictionary into the HTTP response
        return {
            "job_id": job_id,
            "status": result_dict.get("status", "FAILED"),
            "inserted_count": result_dict.get("inserted_count", 0),
            "error": result_dict.get("error", "Unknown processing error")
        }

    except Exception as e:
        return {
            "job_id": job_id,
            "status": "FAILED",
            "error": f"Infrastructure failure: {str(e)}"
        }
