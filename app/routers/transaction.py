from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.ledger_parser import parse_excel_payload, save_transactions_to_db
from app.services.ledger_queries import fetch_transaction
from app.schemas.transaction import TransactionResponse
from app.core.dependencies import get_current_user
from app.models.user import User

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post("/upload")
async def upload_ledger(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):

    validated_records = await parse_excel_payload(file, current_user.id)
    inserted_count = await save_transactions_to_db(
        db, validated_records, current_user.id
    )

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "user_email": current_user.email,
        "message": "File successfully passed the airlock.",
        "records_processed": inserted_count,
    }


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
