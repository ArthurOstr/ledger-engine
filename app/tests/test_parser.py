import io
import pytest
import pandas as pd
from decimal import Decimal
from fastapi import HTTPException

from app.services.ledger_parser import detect_bank_source, parse_excel_payload
from app.models.transaction import BankSource


# --- MOCK DATA FACTORY ---

def create_mock_excel(data: dict, include_garbage_header: bool = False) -> bytes:
    """Generates a raw Excel file in memory to simulate user uploads."""
    df = pd.DataFrame(data)
    output = io.BytesIO()

    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        if include_garbage_header:
            # Simulate the weird empty rows banks sometimes put at the top
            garbage = pd.DataFrame([["Bank Statement", "Confidential"], ["---", "---"]])
            garbage.to_excel(writer, index=False, header=False, startrow=0)
            df.to_excel(writer, index=False, startrow=2)
        else:
            df.to_excel(writer, index=False)

    return output.getvalue()


# Exact column architectures required by your translation matrices
MONO_DATA = {
    "Дата i час операції": ["01.05.2026 14:30:00", "02.05.2026 10:15:00"],
    "Деталі операції": ["Аврора", "Steam"],
    "MCC": [5411, 7993],
    "Сума в валюті картки (UAH)": ["-150.50", "-300.00"],
    "Валюта": ["UAH", "UAH"],
    "Сума в валюті операції": ["-150.50", "-300.00"],
    "Залишок після операції": ["1000.00", "700.00"],
    "Курс": ["—", "39.50"],
    "Сума комісій (UAH)": ["0", "0"],
    "Сума кешбеку (UAH)": ["0", "0"]
}

PRIVAT_DATA = {
    "Дата": ["01.05.2026", "02.05.2026"],
    "Категорія": ["Продукти", "Кафе"],
    "Картка": ["*1234", "*1234"],
    "Опис операції": ["Супермаркет", "Ресторан"],
    "Сума в валюті картки": ["-200.00", "-400.00"],
    "Валюта картки": ["UAH", "UAH"],
    "Сума в валюті транзакції": ["-200.00", "-400.00"],
    "Валюта транзакції": ["UAH", "UAH"],
    "Залишок на кінець періоду": ["2000.00", "1600.00"],
    "Валюта залишку": ["UAH", "UAH"]
}


# --- UNIT TESTS: ROUTER IDENTIFICATION ---

def test_detect_bank_source_mono():
    df = pd.DataFrame(MONO_DATA)
    assert detect_bank_source(df) == BankSource.MONOBANK


def test_detect_bank_source_privat():
    df = pd.DataFrame(PRIVAT_DATA)
    assert detect_bank_source(df) == BankSource.PRIVATBANK


def test_detect_bank_source_unknown_rejected():
    df = pd.DataFrame({"Unknown Column": [1, 2], "Random Data": ["A", "B"]})
    with pytest.raises(HTTPException) as excinfo:
        detect_bank_source(df)
    assert excinfo.value.status_code == 400
    assert "Unknown statement architecture" in excinfo.value.detail


# --- INTEGRATION TESTS: THE PIPELINE ---

def test_parse_excel_payload_mono_success():
    # Includes garbage rows to prove the _extract_raw_dataframe scanner works
    file_bytes = create_mock_excel(MONO_DATA, include_garbage_header=True)
    test_user_id = 1

    # Mocking the custom rules fetched from the database
    mock_user_rules = {
        "steam": "Розваги",
        "аврора": "Дім та ремонт"
    }

    # Passing the new required user_rules argument
    transactions = parse_excel_payload(file_bytes, test_user_id, user_rules=mock_user_rules)

    assert len(transactions) == 2
    assert transactions[0].bank == BankSource.MONOBANK
    assert transactions[0].currency == "UAH"
    assert transactions[0].amount == Decimal("-150.50")
    # Proves regex category rule worked ("аврора" -> "Дім та ремонт")
    assert transactions[0].category == "Дім та ремонт"

    assert transactions[0].exchange_rate is None
    assert transactions[1].exchange_rate == Decimal("39.50")


def test_parse_excel_payload_privat_success():
    file_bytes = create_mock_excel(PRIVAT_DATA)
    test_user_id = 1

    # Empty rules dict for tests that don't rely on custom text matching
    transactions = parse_excel_payload(file_bytes, test_user_id, user_rules={})

    assert len(transactions) == 2
    assert transactions[0].bank == BankSource.PRIVATBANK
    assert transactions[0].amount == Decimal("-200.00")
    assert transactions[0].category == "Продукти"


def test_parse_excel_payload_corrupted_file():
    garbage_bytes = b"This is not an excel file, this is just a string."
    test_user_id = 1

    with pytest.raises(HTTPException) as excinfo:
        parse_excel_payload(garbage_bytes, test_user_id, user_rules={})

    assert excinfo.value.status_code == 400
    assert "Failed to parse Excel file" in excinfo.value.detail


def test_hash_id_determinism():
    file_bytes = create_mock_excel(MONO_DATA)
    test_user_id = 99

    # Parse the exact same file twice
    transactions_run_1 = parse_excel_payload(file_bytes, test_user_id, user_rules={})
    transactions_run_2 = parse_excel_payload(file_bytes, test_user_id, user_rules={})

    # The cryptographic hashes must be mathematically identical
    assert transactions_run_1[0].hash_id == transactions_run_2[0].hash_id
    assert transactions_run_1[1].hash_id == transactions_run_2[1].hash_id