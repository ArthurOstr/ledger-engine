import io
import pytest
import pandas as pd
from sqlalchemy import text
from sqlalchemy.future import select

from tests.conftest import TestingSessionLocal
from app.worker import process_excel_file
from app.models.user import User
from app.models.transaction import Transaction
from app.models.category_rule import CategoryRule

pytestmark = pytest.mark.asyncio

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

async def test_worker_process_excel_file():
    async with TestingSessionLocal() as db:

        # Forge a user and a custom rule using your exact models
        user = User(email="worker_test@example.com", hashed_password="hashed")
        db.add(user)
        await db.commit()
        await db.execute(text(f"SELECT set_config('app.current_user_id', '{user.id}', true)"))

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
        test_context = {"db_session": db}

        # 2. Execute the background worker directly
        result = await process_excel_file(ctx=test_context, file_bytes=file_bytes, user_id=user.id)

    assert result["status"] == "SUCCESS"
    assert result["inserted_count"] == 1
    assert result["error"] is None

    # 3. Mathematically prove the worker successfully injected the rules into the parser
    async with TestingSessionLocal() as db:
        result = await db.execute(select(Transaction).where(Transaction.owner_id == user.id))
        tx = result.scalars().first()

        assert tx is not None
        assert tx.amount == -150.50
        assert tx.category == "Custom Home Repair"
