from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import select, text

from app.models.transaction import Transaction
from app.models.user import User
from app.services.transfer_detector import detect_and_mark_transfers
from tests.conftest import TestingSessionLocal

pytestmark = pytest.mark.asyncio


async def test_detects_cross_bank_self_transfer():
    async with TestingSessionLocal() as db:
        user = User(email="transfer_test@example.com", hashed_password="hashed")
        db.add(user)
        await db.commit()
        await db.execute(text(f"SELECT set_config('app.current_user_id', '{user.id}', true)"))

        base_time = datetime(2026, 10, 15, 14, 0, 0)

        mono_out = Transaction(
            owner_id=user.id,
            date=base_time,
            bank="monobank",
            card="4441 **** **** 0233",
            description="Переказ на картку",
            mcc=4829,
            amount=Decimal("-5000.00"),
            transaction_amount=Decimal("-5000.00"),
            balance_after=Decimal("15000.00"),
            currency="UAH",
            balance_currency="UAH",
            transaction_currency="UAH",
            hash_id="hash_mono_out_1",
        )
        privat_in = Transaction(
            owner_id=user.id,
            date=base_time + timedelta(minutes=3),
            bank="privatbank",
            card="5168 **** **** 8142",
            description="Поповнення картки",
            amount=Decimal("5000.00"),
            transaction_amount=Decimal("5000.00"),
            balance_after=Decimal("12000.00"),
            currency="UAH",
            balance_currency="UAH",
            transaction_currency="UAH",
            hash_id="hash_privat_in_1",
        )
        # Unrelated grocery expense of same magnitude (>24h later, non-transfer keyword)
        unrelated_expense = Transaction(
            owner_id=user.id,
            date=base_time + timedelta(days=3),
            bank="monobank",
            card="4441 **** **** 0233",
            description="Сільпо",
            mcc=5411,
            amount=Decimal("-5000.00"),
            transaction_amount=Decimal("-5000.00"),
            balance_after=Decimal("10000.00"),
            currency="UAH",
            balance_currency="UAH",
            transaction_currency="UAH",
            hash_id="hash_silpo_1",
        )

        db.add_all([mono_out, privat_in, unrelated_expense])
        await db.commit()

        marked = await detect_and_mark_transfers(db, user.id)
        assert marked == 2

        rows = (await db.execute(select(Transaction).where(Transaction.owner_id == user.id))).scalars().all()
        by_hash = {r.hash_id: r for r in rows}

        assert by_hash["hash_mono_out_1"].is_transfer is True
        assert by_hash["hash_privat_in_1"].is_transfer is True
        assert by_hash["hash_silpo_1"].is_transfer is False