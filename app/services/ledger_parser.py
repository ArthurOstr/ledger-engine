import pandas as pd
import io
import hashlib
import re
from decimal import Decimal
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.models.transaction import BankSource, Transaction
from app.schemas.transaction import TransactionBase, TransactionCreate

# Code provided by Mono to sort transactions
MCC_MAPPING = {
    5411: "Супермаркети та продукти",
    5814: "Кафе та ресторани",
    5812: "Кафе та ресторани",
    4121: "Транспорт",
    5541: "Авто",
    5542: "Авто",
    5912: "Аптеки та медицина",
    8099: "Аптеки та медицина",
}

CATEGORY_RULES = {
    "steam": "Розваги",
    "аврора": "Дім та ремонт",
    "зняття готівки": "Зняття готівки",
    "переказ": "Перекази",
    "від:": "Перекази",
    "на свою картку": "Перекази",
}

# Column type definitions
DECIMAL_COLUMNS = [
    "amount",
    "transaction_amount",
    "balance_after",
    "commissions",
    "cashback",
    "exchange_rate",
]
DATE_COLUMNS = ["date"]

# bank translation matrices(dicts)
MONO_MAPPING = {
    "Дата i час операції": "date",
    "Деталі операції": "description",
    "MCC": "mcc",
    "Сума в валюті операції": "transaction_amount",
    "Валюта": "transaction_currency",
    "Курс": "exchange_rate",
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
def detect_bank_source(df: pd.DataFrame) -> BankSource:
    """Inspects the columns of the uploaded dataframe to indentify the bank"""
    headers = set(df.columns)
    if "Дата і час операції" in headers or "MCC" in headers:
        return BankSource.MONOBANK
    if "Сума в валюті картки" in headers or "Валюта залишку" in headers:
        return BankSource.PRIVATBANK
    raise HTTPException(
        status_code=400,
        detail="Unknown statement architecture. Airlock rejected layout.",
    )

# Generating hash to avoid duplicating data
def generate_row_hash(
    user_id: int,
    bank: BankSource,
    date: pd.Timestamp,
    amount: Decimal,
    description: str,
) -> str:
    raw_string = f"{user_id}|{bank}|{date}|{amount}|{str(description).strip()}"
    return hashlib.sha256(raw_string.encode("utf-8")).hexdigest()

# --- MODULAR DATA PARSING ---
# Extraction
def _extract_raw_dataframe(contents: bytes) -> pd.DataFrame:
    """Extract raw dataframe from uploaded contents and find true header"""
    # Reads the file adn turn it into a raw pandas dataframe
    raw_df = pd.read_excel(io.BytesIO(contents), header=None)

    # Scan the top 50 rows to find the exact index of real column
    header_row_index = None
    for idx, row in raw_df.head(50).iterrows():
        row_strings = " ".join(row.dropna().astype(str).tolist())

        # Check if Monobank or Privatbank anchors remain
        if (
                "Дата і час операції" in row_strings
                or "Сума в валюті картки" in row_strings
        ):
            header_row_index = idx
            break

    # if the loop finishes without an anchor, reject the file with known Exception
    if header_row_index is None:
        raise HTTPException(
            status_code=400, detail="400: Unknown statement architecture"
        )

    # Re-read the file, dropping head_row_index
    df = pd.read_excel(io.BytesIO(contents), header=header_row_index)
    # For proper date parsing

    df.columns = (
        df.columns.astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    )
    return df

# Translation
def _apply_bank_schema(df: pd.DataFrame) -> tuple[pd.DataFrame, BankSource]:
    # Route the file into the correct processing frame
    bank = detect_bank_source(df)

    if bank == BankSource.MONOBANK:
        extracted_currency = "UAH"
        dynamic_renames = {}

        # Regex scanner
        for col in df.columns:
            col_str = str(col)
            # Capture 3 letters that matter to find the currency we need
            amount_match = re.search(r"Сума в валюті картки \(([A-Z]{3})\)", col_str)

            if amount_match:
                extracted_currency = amount_match.group(1)
                dynamic_renames[col_str] = "amount"
            elif col_str.startswith("Сума комісій"):
                dynamic_renames[col_str] = "commissions"
            elif col_str.startswith("Сума кешбеку"):
               dynamic_renames[col_str] = "cashback"

    # Apply translation
        df = df.rename(columns=dynamic_renames)
        df = df.rename(columns=MONO_MAPPING)

        # Injects dynamically extracted currency into every row
        df["currency"] = extracted_currency

    else:
        df = df.rename(columns=PRIVAT_MAPPING)

    # Define the strict architecture of what is allowed to pass
    FINAL_COLUMNS = [
            "date", "category", "card", "description", "amount", "currency",
            "transaction_amount", "transaction_currency", "balance_after",
            "balance_currency", "mcc", "commissions", "cashback", "exchange_rate"
    ]

    existing_cols = [col for col in FINAL_COLUMNS if col in df.columns]
    df_clean = df[existing_cols].copy()

    # Preventing KeyError if mapping fails to secure a column head. THE AIRLOCK
    if "amount" not in df_clean.columns:
        raise HTTPException(
            status_code=400,
            detail="Critical error: Primary amount column couldn't be translated"
        )

    # Purge empty or corrupted rows
    df_clean = df_clean.dropna(subset=["amount"])
    return df_clean, bank

# Sanitization
def _sanitize_data(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans dates and decimals"""
    # Type normalization: DATES
    for col in DATE_COLUMNS:
        if col in df.columns:
            # 1. Force to string and scrub invisible spaces
            df[col] = df[col].astype(str).str.strip()

            # 2. Parse safely. 'coerce' turns unreadable garbage into NaT instead of crashing.
            df[col] = pd.to_datetime(
                df[col], dayfirst=True, errors="coerce"
            )
    # Type normalization: DECIMALS
    for col in DECIMAL_COLUMNS:
        if col in df.columns:
            # Strip spaces, turn column to string
            df[col] = (
                df[col]
                .astype(str)
                .str.replace(r"\s+", "", regex=True)
                .str.replace(",", ".")
            )
            # Erasing anomalies such as dashes, NaN, and empty values
            df[col] = df[col].apply(
                lambda x: None if x in ("—", "–", "nan", "None", "") else Decimal(x)
            )
    return df

# Categorization data(Cascade way to do that)
def _apply_categorization(df: pd.DataFrame, bank: BankSource) -> pd.DataFrame:
    """Applies MCC-first, text is the second"""

    # Column validation
    if "category" not in df.columns:
        df["category"] = None

    def determine_category(row):
        # Privatbank native check
        if pd.notna(row.get("category")) and str(row.get("category")).strip() != "":
            return str(row["category"]).strip()

        # Monobank MCC code lookup
        if pd.notna(row.get("mcc:")):
            try:
                # Pandas could save floats instead of integers(such as 5411.0)
                mcc_code = int(float(row["mcc"]))
                if mcc_code in MCC_MAPPING:
                    return MCC_MAPPING[mcc_code]

            except (ValueError, TypeError):
                pass

        # Text matching fallback
        desc = str(row.get("description", "")).lower()
        for keyword, assigned_category in CATEGORY_RULES.items():
            if keyword in desc:
                return assigned_category

        return "Інше"

    # Apply logic row by row
    df["category"] = df.apply(determine_category, axis=1)

    return df

# Enrichment and aligning
def _enrich_and_hash(df: pd.DataFrame, user_id: int, bank: BankSource) -> list[dict]:
    """Injects missing fields and applies the cryptographic hash"""

    # Data patching(to consolidate the data from different types of statement)
    if "balance_currency" not in df.columns:
        df["balance_currency"] = "UAH"

    # Neutralize remaining Nan to avoid SQLAlchemy crashes
    df = df.where(pd.notnull(df), None)

    # Inject architectural metadata
    df["bank"] = bank
    # Applying hash to the DataFrame
    df["hash_id"] = df.apply(
        lambda row: generate_row_hash(
            user_id, bank, row["date"], row["amount"], row.get("description", "")
        ),
        axis=1,
    )

    return df.to_dict(orient="records")

def parse_excel_payload(contents: bytes, user_id: int) -> list[TransactionCreate]:
    """The main assembly line for incoming Excel files"""
    try:
        # 1. Extract
        df = _extract_raw_dataframe(contents)

       # 2. Translate
        df, bank = _apply_bank_schema(df)

        # 3. Sanitize
        df = _sanitize_data(df)

        # 4. Categorize
        df = _apply_categorization(df, bank)

        # 5. Enrich and hash
        raw_records = _enrich_and_hash(df, user_id, bank)

        return [TransactionCreate(**record) for record in raw_records]

    except HTTPException:
        raise

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
