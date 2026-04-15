from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.ledger_parser import parse_excel_payload, save_transactions_to_db

router = APIRouter(prefix="/api/transactions", tags=["transactions"])


@router.post("/upload")
async def upload_ledger(
    file: UploadFile = File(...), db: AsyncSession = Depends(get_db)
):

    validated_records = await parse_excel_payload(file)
    inserted_count = await save_transactions_to_db(db, validated_records)

    return {
        "filename": file.filename,
        "content_type": file.content_type,
        "message": "File succesfully passed the airlock.",
        "records_processed": inserted_count,
    }
