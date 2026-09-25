import uuid
from pathlib import Path
import logging
import aiofiles
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from arq.jobs import Job, JobStatus

from app.database import get_db
from app.services.ledger_queries import fetch_transaction
from app.schemas.transaction import TransactionResponse
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.storage import storage

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("/tmp/statement_uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

router = APIRouter(prefix="/api/transactions", tags=["transactions"])

async def get_redis_pool(request: Request):
    return request.app.state.redis_pool

@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_ledger(
    file: UploadFile = File(...),
    redis_pool=Depends(get_redis_pool),
    current_user: User = Depends(get_current_user),
):
    # Shield from non-Excel files
    if not file.filename.endswith((".xls", ".xlsx")):
        logger.warning(
            f"Upload rejected from User [{current_user.id}] due to file extension [{file.filename}]."
        )
        raise HTTPException(
            status_code=400, detail="Invalid file type. Only .xls or .xlsx allowed"
        )

    ref_key = None

    try:
        file_bytes = await file.read()
        file_size = len(file_bytes)
        if file_size == 0:
            logger.warning(
                f"Upload rejected for User [{current_user.id}]: '{file.filename}' is empty"
            )
            raise HTTPException(status_code=400, detail="Uploaded file is empty")

        file_key = f"uploads/{uuid.uuid4().hex}_{file.filename}"
        ref_key = await storage.put(file_key, file_bytes)

        # Drop payload into the Redis Broker. It must match redis config(currently worker.py)
        job = await redis_pool.enqueue_job(
            "process_excel_file",
            file_path=ref_key,
            user_id=current_user.id
        )

        logger.info(
            f"Enqueued job [{job.job_id}] for User [{current_user.id}]:"
            f"file='{file.filename}' ({file_size} bytes) -> ref_key='{ref_key}'"
        )

        return {
            "filename": file.filename,
            "user_email": current_user.email,
            "message": "File successfully queued for background processing.",
            "job_id": job.job_id,
            "status": "queued",
        }

    except HTTPException:
        if ref_key:
            await storage.delete(ref_key)
        raise

    except Exception as e:
        logger.exception(
            f"Failed to stage upload for User [{current_user.id}], file='{file.filename}': {str(e)}"
        )
        if ref_key:
            await storage.put(ref_key)

        raise HTTPException(status_code=500, detail=f"Broker rejection or storage failure: {str(e)}")


@router.get("", response_model=list[TransactionResponse])
async def get_transaction(
    limit: int = 5000,
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
