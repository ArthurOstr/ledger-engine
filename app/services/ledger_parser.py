import pandas as pd
import io
import hashlib
from decimal import Decimal
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.transaction import Transaction
from app.schemas.transaction import TransactionBase, TransactionCreate

DECIMAL_COLUMNS = ["amount", "transaction_amount", "balance_after"]
DATE_COLUMNS = ["date"]

BANK_MAPPING = {
    "Дата": "date",
    "Категорія": "category",
    "Картка": "card",
    "Опис операції": "description",
    "Сума в валюті картки": "amount",
    "Валюта картки": "currency",
    "Сума в валюті транзакції": "transaction_amount",
    "Валюта транзакції": "transaction_currency",
    "Залишок на кінець періоду": "balance_after",
    "Валюта залишку": "balance_currency",
}


def generate_row_hash(date: pd.Timestamp, amount: Decimal, description: str) -> str:
    raw_string = f"{date}|{amount}|{str(description).strip()}"
    return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()


async def parse_excel_payload(file: UploadFile) -> list[TransactionCreate]:
    contents = await file.read()

    try:
        df = pd.read_excel(io.BytesIO(contents), header=1)

        df = df.rename(columns=BANK_MAPPING)
        existing_cols = [col for col in BANK_MAPPING.values() if col in df.columns]
        df_clean = df[existing_cols].copy()

        df_clean = df_clean.dropna(subset=["amount"])

        for col in DATE_COLUMNS:
            if col in df_clean.columns:
                df_clean[col] = pd.to_datetime(
                    df_clean[col], format="%d.%m.%Y %H:%M:%S"
                ).dt.to_pydatetime()

        for col in DECIMAL_COLUMNS:
            if col in df_clean.columns:
                df_clean[col] = df_clean[col].astype(str).apply(Decimal)

        df_clean = df_clean.where(pd.notnull(df_clean), None)

        # Applying hash to the DataFrame
        df_clean["hash_id"] = df_clean.apply(
            lambda row: generate_row_hash(
                row["date"], row["amount"], row["description"]
            ),
            axis=1,
        )
        raw_records = df_clean.to_dict(orient="records")

        validated_transactions = []
        for record in raw_records:
            validated_transactions.append(TransactionCreate(**record))

        return validated_transactions

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse Excel file: {str(e)}"
        )


async def save_transactions_to_db(
    db: AsyncSession, transactions: list[TransactionCreate]
):
    # Pydantic models to dictionaries
    values_to_insert = [record.model_dump() for record in transactions]

    if not values_to_insert:
        return 0

    # Special postgresql Insert statement
    stmt = insert(Transaction).values(values_to_insert)

    # Ignore duplicated hash_id
    stmt = stmt.on_conflict_do_nothing(index_elements=["hash_id"])
    result = await db.execute(stmt)
    await db.commit()

    return result.rowcount
