import pandas as pd
import io
import hashlib
from decimal import Decimal
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.transaction import BankSource, Transaction
from app.schemas.transaction import TransactionBase, TransactionCreate

# Column type definitions
DECIMAL_COLUMNS = ["amount", "transaction_amount", "balance_after"]
DATE_COLUMNS = ["date"]

# bank translation matrices(dicts)
MONO_MAPPING = {
    "Дата і час операції": "date",
    "Деталі операції": "description",
    "MCC": "mcc",
    "Сума в валюті картки (UAH)": "amount",
    "Сума в валюті операції": "transaction_amount",
    "Валюта": "transaction_currency",
    "Курс": "exchange_rate",
    "Сума комісій (UAH)": "commission",
    "Сума кешбеку (UAH)": "cashback",
    "Залишок після операції": "balance_after",
}

PRIVAT_MAPPING = {
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


# origin router
def detect_bank_source(df: pd.DataFrame) -> str:
    """Inspects the columns of the uploaded dataframe to indentify the bank"""
    headers = set(df.columns)
    if "Дата і час операції" in headers or "MCC" in headers:
        return "monobank"
    if "Сума в валюті картки" in headers or "Валюта залишку" in headers:
        return "privatbank"
    raise HTTPException(
        status_code=400,
        detail="Unknown statement architecture. Airlock rejected layout.",
    )


def generate_row_hash(
    user_id: int,
    bank: BankSource,
    date: pd.Timestamp,
    amount: Decimal,
    description: str,
) -> str:
    raw_string = f"{user_id}|{bank}|{date}|{amount}|{str(description).strip()}"
    return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()


async def parse_excel_payload(
    file: UploadFile, user_id: int
) -> list[TransactionCreate]:
    contents = await file.read()

    try:
        # Reads the file adn turn it into a raw pandas dataframe
        df = pd.read_excel(io.BytesIO(contents))
        headers = set(df.columns)

        # If valid headers aren't found, try Row 1 (PrivatBank default)
        if not ("Дата і час операції" in headers or "Сума в валюті картки" in headers):
            df = pd.read_excel(io.BytesIO(contents), header=1)

        # Route the file into the correct processing frame
        bank = detect_bank_source(df)
        mapping = MONO_MAPPING if bank == BankSource.MONOBANK else PRIVAT_MAPPING

        # Apply translation
        df = df.rename(columns=mapping)
        existing_cols = [col for col in mapping.values() if col in df.columns]
        df_clean = df[existing_cols].copy()

        # Purge empty or corrupted rows
        df_clean = df_clean.dropna(subset=["amount"])

        # Type normalization: DATES
        for col in DATE_COLUMNS:
            if col in df_clean.columns:
                df_clean[col] = pd.to_datetime(
                    df_clean[col], dayfirst=True
                ).dt.to_pydatetime()

        # Type normalization: DECIMALS
        for col in DECIMAL_COLUMNS:
            if col in df_clean.columns:
                # Strip spaces, turn column to string
                df_clean[col] = df_clean[col].astype(str).str.replace(r"\s+", "", regex=True).str.replace(",", ".")

                # Erasing anomalies such as dashes, NaN, and empty values
                df_clean[col] = df_clean[col].apply(
                    lambda x: None if x in ("—", "–", "nan", "None", "") else Decimal(x)
                )

        # Data patching(to consolidate the data from different types of statement)
        if bank == BankSource.MONOBANK:
            if "currency" not in df_clean.columns:
                df_clean["currency"] = "UAH"
        if "balance_currency" not in df_clean.columns:
            df_clean["balance_currency"] = "UAH"

        # Neutralize remaining Nan to avoid SQLAlchemy crashes
        df_clean = df_clean.where(pd.notnull(df_clean), None)

        # Inject architectural metadata
        df_clean["bank"] = bank

        # Applying hash to the DataFrame
        df_clean["hash_id"] = df_clean.apply(
            lambda row: generate_row_hash(
                user_id, bank, row["date"], row["amount"], row.get("description", "")
            ),
            axis=1,
        )

        # Convert the DatatFrame to and array
        raw_records = df_clean.to_dict(orient="records")

        # Transfer through Pydantic validation airlock
        validated_transactions = []
        for record in raw_records:
            validated_transactions.append(TransactionCreate(**record))

        return validated_transactions

    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to parse Excel file: {str(e)}"
        )


async def save_transactions_to_db(
    db: AsyncSession, transactions: list[TransactionCreate], user_id: int
):
    # Pydantic models to dictionaries
    values_to_insert = []
    for record in transactions:
        record_dict = record.model_dump()
        record_dict["owner_id"] = user_id
        values_to_insert.append(record_dict)

    if not values_to_insert:
        return 0

    # Special postgresql Insert statement
    stmt = insert(Transaction).values(values_to_insert)

    # Ignore duplicated hash_id
    stmt = stmt.on_conflict_do_nothing(index_elements=["hash_id"])
    result = await db.execute(stmt)
    await db.commit()

    return result.rowcount
