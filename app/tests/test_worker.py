import io
import pandas as pd
from unittest.mock import patch
from sqlalchemy.future import select

from app.tests.conftest import TestingSessionLocal
from app.worker import process_excel_file
from app.models.user import User
from app.models.transaction import Transaction

# --- MOCK FACTORY ---
def create_mock_excel() -> bytes:
    # Strictly aligned with your current test_parser.py and ledger_parser.py columns
    data = {
        "Дата i час операції": ["01.05.2026 14:30:00"],
        "Деталі операції": ["Аврора"],
        "MCC": [5411],
        "Сума в валюті картки (UAH)": ["-150.50"],
        "Валюта": ["UAH"],
        "Сума в валюті операції": ["-150.50"],
        "Залишок після операції": ["1000.00"],
        "Курс": ["—"],
        "Сума комісій (UAH)": ["0"],
        "Сума кешбеку (UAH)": ["0"]
    }
    df = pd.DataFrame(data)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


# --- TESTS: WORKER EXECUTION ---

# Patch the worker's internal database session to strictly use our isolated test engine
@patch("app.worker.AsyncSessionLocal", new=TestingSessionLocal)
async def test_worker_process_excel_file():
    # 1. Forge a user and a custom rule using your exact models
    async with TestingSessionLocal() as db:
        user = User(email="worker_test@example.com", hashed_password="hashed")
        db.add(user)
        await db.commit()

        # We tell the engine that "аврора" should override the bank's MCC
        rule =  CategoryRule(
            owner_id=user.id,
            keyword="аврора",
            assigned_category="Custom Home Repair",
            is_active=True
        )
        db.add(rule)
        await db.commit()

    file_bytes = create_mock_excel()

    # 2. Execute the background worker directly
    result_message = await process_excel_file(ctx={}, file_bytes=file_bytes, user_id=user.id)

    assert "Processed 1 transactions." in result_message

    # 3. Mathematically prove the worker successfully injected the rules into the parser
    async with TestingSessionLocal() as db:
        result = await db.execute(select(Transaction).where(Transaction.owner_id == user.id))
        tx = result.scalars().first()

        assert tx is not None
        assert tx.amount == -150.50
        assert tx.category == "Custom Home Repair"