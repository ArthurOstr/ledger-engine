from fastapi import HTTPException
import pandas as pd

from app.models.transaction import BankSource
from app.schemas.transaction import TransactionCreate
from app.services.parsers.base import BaseBankParser, _extract_raw_dataframe
from app.services.parsers.monobank import MonobankParser
from app.services.parsers.privatbank import PrivatBankParser

PARSERS: list[BaseBankParser] = [
    MonobankParser(),
    PrivatBankParser(),
]

def get_parser_for_dataframe(df: pd.DataFrame) -> BaseBankParser:
    """Finds the registered bank strategy matching the DataFrame's headers."""
    headers = set(df.columns)
    for parser in PARSERS:
        if parser.matches(headers):
            return parser

    raise HTTPException(
        status_code=400,
        detail="Unknown statement architecture. Airlock rejected layout.",
    )


def detect_bank_source(df: pd.DataFrame) -> BankSource:
    """Public helper matching the historical detect_bank_source interface."""
    return get_parser_for_dataframe(df).bank_source


def parse_excel_payload(
    contents: bytes, user_id: int, user_rules: dict[str, str]
) -> list[TransactionCreate]:
    """Single-pass ingestion pipeline: extract -> detect parser -> execute strategy."""
    all_anchors = set().union(*(p.row_anchors for p in PARSERS))

    # Single-pass table extraction
    df = _extract_raw_dataframe(contents, header_anchors=all_anchors)

    # Strategy lookup
    parser = get_parser_for_dataframe(df)

    # Execution
    return parser.parse(df, user_id=user_id, user_rules=user_rules)