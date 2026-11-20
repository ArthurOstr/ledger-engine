import re
from fastapi import HTTPException
import pandas as pd

from app.models.transaction import BankSource
from app.services.parsers.base import BaseBankParser
from app.services.parsers.mcc import resolve_mcc_category

MONO_MAPPING = {
    "Дата i час операції": "date",  # Latin i (\u0069)
    "Деталі операції": "description",
    "MCC": "mcc",
    "Сума в валюті операції": "transaction_amount",
    "Валюта": "transaction_currency",
    "Курс": "exchange_rate",
    "Залишок після операції": "balance_after",
}

class MonobankParser(BaseBankParser):
    @property
    def bank_source(self) -> BankSource:
        return BankSource.MONOBANK

    @property
    def header_signatures(self) -> set[str]:
        return {"Дата і час операції", "Дата i час операції", "MCC"}

    @property
    def row_anchors(self) -> set[str]:
        return {"MCC", "Дата і час операції", "Дата i час операції"}

    @staticmethod
    def resolve_bank_category(row: pd.Series) -> str | None:
        if pd.notna(row.get("mcc")):
            try:
                mcc_code = int(float(row["mcc"]))
                return resolve_mcc_category(mcc_code)
            except (ValueError, TypeError):
                pass
        return None

    def translate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        # Collapse newlines/extra spaces in Excel headers before matching
        df = df.copy()
        df.columns = [re.sub(r"\s+", " ", str(c)).strip() for c in df.columns]

        extracted_currency = "UAH"
        dynamic_renames = {}

        # Regex scanner for dynamic currency header
        for col in df.columns:
            col_str = str(col)
            # Capture 3 letters that matter to find the currency we need
            amount_match = re.search(r"Сума\s+[ву]\s+валюті\s+картки\s*\(([A-Z]{3})\)", col_str)

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

        # Extraction preamble text
        preamble = str(df.attrs.get("preamble", ""))
        extracted_card = None
        card_match = re.search(r"(\d{4})\s*(?:\*+\s*)+(\d{4})", preamble)
        if card_match:
            extracted_card = f"{card_match.group(1)} **** **** {card_match.group(2)}"

        # Injects dynamically extracted currency into every row
        df["card"] = extracted_card
        df["currency"] = extracted_currency

        if "balance_currency" not in df.columns:
            df["balance_currency"] = df.get("currency", "UAH")
        if "transaction_currency" not in df.columns:
            df["transaction_currency"] = df.get("currency", "UAH")

        # Define the strict architecture of what is allowed to pass
        final_cols = [
            "date", "category", "card", "description", "amount", "currency",
            "transaction_amount", "transaction_currency", "balance_after",
            "balance_currency", "mcc", "commissions", "cashback", "exchange_rate"
        ]
        df_clean = df[[c for c in final_cols if c in df.columns]].copy()

        # Airlock: fail cleanly with 400 if either required column failed to map
        missing_required = {"date", "amount"} - set(df_clean.columns)
        if missing_required:
            raise HTTPException(
                status_code=400,
                detail=f"Critical error: Required columns missing after translation: {sorted(missing_required)}"
            )

        # Purge summary/footer rows missing a date or amount
        return df_clean.dropna(subset=["date", "amount"])