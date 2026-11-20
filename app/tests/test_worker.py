import io
import uuid
from pathlib import Path
from decimal import Decimal

import openpyxl
import pytest
import pandas as pd
from sqlalchemy import select, text

from tests.conftest import TestingSessionLocal
from app.worker import process_excel_file
from app.models.user import User
from app.models.transaction import Transaction
from app.models.category_rule import CategoryRule
from app.services.storage import storage

pytestmark = pytest.mark.asyncio

# --- MOCK FACTORY ---
def create_mock_excel(include_card_preamble: bool = True) -> bytes:
    """Generates a realistic in-memory Monobank statement with preamble metadata."""
    wb = openpyxl.Workbook()
    ws = wb.active

    if include_card_preamble:
        ws.append(["Виписка за період: 01.05.2026 - 31.05.2026"])
        ws.append(["Інформація по картці: 4441 **** **** 0233"])
        ws.append(["Валюта: UAH"])

    headers = [
        "Дата i час операції",
        "Деталі операції",
        "MCC",
        "Сума в валюті картки (UAH)",
        "Валюта",
        "Сума в валюті операції",
        "Залишок після операції",
        "Курс",
        "Сума комісій (UAH)",
        "Сума кешбеку (UAH)"
    ]
    ws.append(headers)

    ws.append([
        "01.05.2026 14:30:00",
        "Аврора",
        5411,
        "-150.50",
        "UAH",
        "-150.50",
        "1000.00",
        "—",
        "0",
        "0",
    ])

    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()


# --- TESTS: WORKER EXECUTION ---

async def test_worker_process_excel_file(tmp_path: Path):
    async with TestingSessionLocal() as db:

        # Forge a user and a custom rule using your exact models
        user = User(email=f"worker_{uuid.uuid4().hex[:6]}@example.com", hashed_password="hashed")
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

        file_key = f"uploads/test_{uuid.uuid4().hex}.xlsx"
        ref_key = await storage.put(file_key, create_mock_excel(include_card_preamble=True))

        test_context = {"db_session": db}

        # 2. Execute the background worker directly
        result = await process_excel_file(ctx=test_context, file_path=str(ref_key), user_id=user.id)

    assert result["status"] == "SUCCESS"
    assert result["inserted_count"] == 1
    assert result["error"] is None

    assert not Path(ref_key).exists(), "Local staging file was not unlinked"
    with pytest.raises(FileNotFoundError):
        await storage.get(ref_key)

    async with TestingSessionLocal() as db:
        await db.execute(
            text(f"SELECT set_config('app.current_user_id', '{user.id}', true)")
        )
        query = select(Transaction).where(Transaction.owner_id == user.id)

        db_result = await db.execute(query)
        tx = db_result.scalars().first()

        assert tx is not None
        assert tx.amount == -150.50
        assert tx.category == "Custom Home Repair"
        assert tx.balance_after == Decimal("1000.00")
        assert tx.card == "4441 **** **** 0233"
        assert tx.hash_id is not None

async def test_worker_deduplication_zero_inserts():
    """Verifies worker handles identical file re-upload without errors (inserted_count == 0)."""
    async with TestingSessionLocal() as db:
        user = User(email=f"dedup_{uuid.uuid4().hex[:6]}@example.com", hashed_password="hashed")
        db.add(user)
        await db.commit()

        excel_bytes = create_mock_excel(include_card_preamble=True)
        test_context = {"db_session": db}

        # First upload: inserts 1 row
        ref_key_1 = await storage.put(f"uploads/test_{uuid.uuid4().hex}.xlsx", excel_bytes)
        res_1 = await process_excel_file(ctx=test_context, file_path=str(ref_key_1), user_id=user.id)
        assert res_1["status"] == "SUCCESS"
        assert res_1["inserted_count"] == 1

        # Second upload of the exact same data: deduplicates, inserts 0 rows
        ref_key_2 = await storage.put(f"uploads/test_{uuid.uuid4().hex}.xlsx", excel_bytes)
        res_2 = await process_excel_file(ctx=test_context, file_path=str(ref_key_2), user_id=user.id)
        assert res_2["status"] == "SUCCESS"
        assert res_2["inserted_count"] == 0
        assert res_2["error"] is None
