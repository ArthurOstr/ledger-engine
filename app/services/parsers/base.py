from abc import ABC, abstractmethod
from decimal import Decimal
import hashlib
import io
import re
from typing import Any
from fastapi import HTTPException
import pandas as pd

from app.models.transaction import BankSource
from app.schemas.transaction import TransactionCreate

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
CURRENCY_COLUMNS = ["currency", "balance_currency", "transaction_currency"]

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

# Sanitization
def sanitize_data(df: pd.DataFrame) -> pd.DataFrame:
    """Cleans dates and decimals"""
    # Type normalization: CURRENCIES
    for col in CURRENCY_COLUMNS:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip().str.upper()
            df.loc[df[col].isin(["NAN", "NONE", ""]), col] = "UAH"

    # Type normalization: DATES
    for col in DATE_COLUMNS:
        if col in df.columns:
            # 1. Force to string and scrub invisible spaces
            df[col] = df[col].astype(str).str.strip()

            # 2. Parse safely. 'coerce' turns unreadable garbage into NaT instead of crashing
            df[col] = pd.to_datetime(
                df[col], dayfirst=True, errors="coerce"
            )

    # prevents NULL/NaT insertion
    valid_date_cols = [c for c in DATE_COLUMNS if c in df.columns]
    if valid_date_cols:
        df = df.dropna(subset=valid_date_cols)

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
                lambda x: None if x in ("—", "–", "nan", "None", "", "-") else Decimal(x)
            )

        # Type normalization: MCC
        if "mcc" in df.columns:
            def _clean_mcc(val):
                if pd.isna(val) or val in ("—", "–", "nan", "None", "", "-"):
                    return None
                try:

                    return f"{int(float(val)):04d}"
                except (ValueError, TypeError):
                    return None

            df["mcc"] = [_clean_mcc(x) for x in df["mcc"]]
            df["mcc"] = df["mcc"].astype(object).where(df["mcc"].notna(), None)
    return df

# Extraction
def _extract_raw_dataframe(contents: bytes, header_anchors: set[str]) -> pd.DataFrame:
    """
    Single-pass Excel reader:
    Extract raw dataframe from uploaded contents and find true header
    """
    try:
        # Reads the file adn turn it into a raw pandas dataframe
        raw_df = pd.read_excel(io.BytesIO(contents), header=None)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to parse Excel file: {str(exc)}"
        ) from exc

    if raw_df.empty:
        raise HTTPException(status_code=400, detail="Failed to parse: Excel file contains no data")

    # Scan the top 50 rows to find the bank anchor keywords
    header_idx: int | None = None
    max_scan = min(len(raw_df), 50)

    for idx in range(max_scan):
        row_string = " ".join(raw_df.iloc[idx].dropna().astype(str).tolist())
        if any(anchor in row_string for anchor in header_anchors):
            header_idx = idx
            break

        if header_idx is not None:
            raise HTTPException(
                status_code=400, detail="Unknown statement architecture"
            )

    # In-memory slice and header promotion
    raw_headers = raw_df.iloc[header_idx].tolist()
    clean_headers = [
        re.sub(r"\s+", " ", str(h)).strip() if pd.notna(h) and str(h).strip() != "" else f"unnamed_{i}"
        for i, h in enumerate(raw_headers)
    ]

    data_df = raw_df.iloc[header_idx + 1 :].copy()
    data_df.columns = clean_headers
    data_df.reset_index(drop=True, inplace=True)
    data_df.dropna(how="all", inplace=True)

    del raw_df
    return data_df

class BaseBankParser(ABC):
    """
    Abstract base class for bank parser
    """

    @property
    @abstractmethod
    def bank_source(self) -> BankSource:
        """The bank enum identifier"""
        pass

    @property
    @abstractmethod
    def header_signatures(self) -> set[str]:
        """Colum names that identify this bank in upl DataFrames"""
        pass

    @property
    @abstractmethod
    def row_anchors(self) -> set[str]:
        """Keywords used in the reader to find the true table header"""
        pass

    def matches(self, headers: set[str]) -> bool:
        """Determines if the extracted column headers match this bank parser"""
        return bool(self.header_signatures & headers)

    @abstractmethod
    def translate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Translates bank-specific column layouts into canonical field names"""
        pass

    @staticmethod
    @abstractmethod
    def resolve_bank_category( row: pd.Series) -> str | None:
        """Bank-specific categorization hook"""
        pass

    def determine_category(self,row: pd.Series, user_rules: dict[str,str]) -> str:
        """Cascading category resolution: User regex rules -> Bank hook -> 'Інше'."""
        desc = str(row.get("description","")).lower()

        # custom user keyword matches
        for keyword, assigned_cat in user_rules.items():
            if keyword in desc:
                return assigned_cat

        # Bank-specific fallback
        bank_cat = self.resolve_bank_category(row)
        if bank_cat:
            return bank_cat

        return "Інше"

    def parse(self, df: pd.DataFrame, user_id:int, user_rules: dict[str,str]
              ) -> list[TransactionCreate]:
        """Template method running translation, sanitization, categorization and hashing"""
        # 1. Translate columns
        df = self.translate_schema(df)

        # 2. Sanitize data types
        df = sanitize_data(df)

        # 3. Categorize
        if "category" not in df.columns:
           df["category"] = None
        df["category"] = df.apply(lambda row: self.determine_category(row, user_rules), axis=1)

        # 4. Defaults and clean nulls
        if "balance_currency" not in df.columns:
            df["balance_currency"] = None
        df = df.where(pd.notnull(df), None)

        # 5. Enrich and hash
        df["bank"] = self.bank_source
        df["hash_id"] = df.apply(
            lambda row: generate_row_hash(
                user_id, self.bank_source, row["date"], row["amount"], row.get("description", "")
            ),
            axis=1,
        )

        records = df.to_dict(orient="records")
        return [TransactionCreate(**record) for record in records]