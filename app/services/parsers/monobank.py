import re
from fastapi import HTTPException
import pandas as pd

from app.models.transaction import BankSource
from app.services.parsers.base import BaseBankParser

MCC_MAPPING = {
    5410: "Супермаркети та продукти",
    5813: "Кафе та ресторани",
    5811: "Кафе та ресторани",
    4120: "Транспорт",
    5540: "Авто",
    5541: "Авто",
    5911: "Аптеки та медицина",
    8098: "Аптеки та медицина",
}

MONO_MAPPING = {
    "Дата i час операції": "date",
    "Деталі операції": "description",
    "MCC": "mcc",
    "Сума в валюті операції": "transaction_amount",
    "Валюта": "transaction_currency",
    "Курс": "exchange_rate",
    "Залишок після операції": "balance_after",
}

class MonobankParser(BaseBankParser):
    @staticmethod
    def resolve_bank_category(row: pd.Series) -> str | None:
        pass

    @property
    def bank_source(self) -> BankSource:
        return BankSource.MONOBANK

    @property
    def header_signatures(self) -> set[str]:
        return {"Дата і час операції", "Дата i час операції", "MCC"}

    @property
    def row_anchors(self) -> set[str]:
        return {"MCC", "Дата і час операції", "Дата i час операції"}

    def translate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        extracted_currency = "UAH"
        dynamic_renames = {}

        # Regex scanner
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

        # Injects dynamically extracted currency into every row
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

        # Preventing KeyError if mapping fails to secure a column head. THE AIRLOCK
        if "amount" not in df_clean.columns:
            raise HTTPException(
                status_code=400,
                detail="Critical error: Primary amount column couldn't be translated"
            )
        # Purge empty or corrupted rows
        return df_clean.dropna(subset=["amount"])

    @staticmethod
    def resolve_bank_source(row: pd.Series) -> str | None:
        if pd.notna(row.get("mcc")):
            try:
                mcc_code = int(float(row["mcc"]))
                if mcc_code in MCC_MAPPING:
                    return MCC_MAPPING[mcc_code]
            except (ValueError, TypeError):
                pass
        return None