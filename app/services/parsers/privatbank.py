from fastapi import HTTPException
import pandas as pd

from app.models.transaction import BankSource
from app.services.parsers.base import BaseBankParser

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


class PrivatBankParser(BaseBankParser):
    @property
    def bank_source(self) -> BankSource:
        return BankSource.PRIVATBANK

    @property
    def header_signatures(self) -> set[str]:
        return {"Сума в валюті картки", "Валюта залишку"}

    @property
    def row_anchors(self) -> set[str]:
        return {"Картка", "Сума в валюті картки"}

    def translate_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.rename(columns=PRIVAT_MAPPING)

        if "currency" not in df.columns:
            df["currency"] = "UAH"
        if "balance_currency" not in df.columns:
            df["balance_currency"] = df.get("currency", "UAH")
        if "transaction_currency" not in df.columns:
            df["transaction_currency"] = df.get("currency", "UAH")

        final_cols = [
            "date", "category", "card", "description", "amount", "currency",
            "transaction_amount", "transaction_currency", "balance_after",
            "balance_currency", "mcc", "commissions", "cashback", "exchange_rate"
        ]
        df_clean = df[[c for c in final_cols if c in df.columns]].copy()

        if "amount" not in df_clean.columns:
            raise HTTPException(
                status_code=400,
                detail="Critical error: Primary amount column couldn't be translated"
            )

        return df_clean.dropna(subset=["amount"])

    def resolve_bank_category(self, row: pd.Series) -> str | None:
        if pd.notna(row.get("category")) and str(row.get("category")).strip() != "":
            return str(row["category"]).strip()
        return None