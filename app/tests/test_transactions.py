import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import text

from app.main import app
from tests.conftest import TestingSessionLocal
from app.routers.transaction import get_redis_pool
from app.models.transaction import Transaction, BankSource
from app.models.user import User

pytestmark = pytest.mark.asyncio

# --- REDIS MOCKING ARCHITECTURE ---
class MockJob:
    def __init__(self, job_id):
        self.job_id = job_id


class MockRedisPool:
    async def enqueue_job(self, function_name, *args, **kwargs):
        # Intercept the ARQ broker call and immediately return a fake job
        return MockJob("mock_job_12345")


async def override_get_redis_pool():
    return MockRedisPool()


# Intercept the FastAPI dependency so we don't need a real Redis container
@pytest.fixture(autouse=True)
def apply_redis_mock():
    app.dependency_overrides[get_redis_pool] = override_get_redis_pool
    yield


# --- HELPER FACTORY ---
async def create_auth_client() -> tuple[AsyncClient, int]:
    """Generates a fresh user, logs them in, and returns an HTTPX client with the HttpOnly cookie attached."""
    email = f"user_{uuid.uuid4()}@example.com"
    password = "secure_vault_key"

    client = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")

    # Mint the user
    await client.post("/api/users/register", json={"email": email, "password": password})
    # Mint the token (HTTPX automatically stores the Set-Cookie response)
    await client.post("/api/users/login", data={"username": email, "password": password})

    # Extract the internal database ID to inject mock records later
    async with TestingSessionLocal() as db:
        from sqlalchemy import select
        result = await db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        user_id = user.id

    return client, user_id


# --- TESTS: THE AIRLOCK & BROKER ---

async def test_upload_invalid_file_type_rejected():
    client, _ = await create_auth_client()

    # Simulate a user trying to breach the airlock with a text file
    files = {'file': ('hack.txt', b"malicious string", 'text/plain')}
    response = await client.post("/api/transactions/upload", files=files)

    assert response.status_code == 400
    assert "Invalid file type" in response.json()["detail"]


async def test_upload_valid_file_triggers_broker():
    client, _ = await create_auth_client()

    # Feed dummy bytes wrapped in an approved Excel extension
    files = {'file': ('ledger.xlsx', b"fake excel bytes",
                      'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}
    response = await client.post("/api/transactions/upload", files=files)

    # 202 Accepted proves the HTTP layer accepted the file and handed it off
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "queued"
    # Proves our Redis mock intercepted the call successfully
    assert data["job_id"] == "mock_job_12345"


# --- TESTS: TENANT ISOLATION ---

async def test_tenant_isolation_get_transactions():
    client_a, user_a_id = await create_auth_client()
    client_b, user_b_id = await create_auth_client()

    # Inject a transaction strictly belonging to User A into the macro-system
    async with TestingSessionLocal() as db:
        await db.execute(text(f"SELECT set_config('app.current_user_id', '{user_a_id}', true)"))
        tx = Transaction(
            owner_id=user_a_id,
            bank=BankSource.MONOBANK,
            amount=Decimal("-100.00"),
            currency="UAH",
            balance_after=Decimal("900.00"),
            transaction_currency="UAH",
            transaction_amount=Decimal("-100.00"),
            date=datetime.now(),
            balance_currency="UAH",
            hash_id=f"hash_{uuid.uuid4()}"
        )
        db.add(tx)
        await db.commit()

    # User A requests their vault. The system must return 1 record.
    resp_a = await client_a.get("/api/transactions")
    assert resp_a.status_code == 200
    assert len(resp_a.json()) == 1
    assert resp_a.json()[0]["amount"] == "-100.00"

    # User B requests their vault. The system must mathematically return 0 records.
    # If this fails, the system is leaking financial data.
    resp_b = await client_b.get("/api/transactions")
    assert resp_b.status_code == 200
    assert len(resp_b.json()) == 0


async def test_tenant_isolation_pagination():
    client, user_id = await create_auth_client()

    # Inject a massive payload to simulate months of heavy banking history
    async with TestingSessionLocal() as db:
        await db.execute(text(f"SELECT set_config('app.current_user_id', '{user_id}', true)"))
        transactions = []
        base_time = datetime.now()
        for i in range(100):
            # Shift the index by 1 to avoid the "-0.00" string serialization quirk
            amount_val = Decimal(f"-{i + 1}.00")
            tx = Transaction(
                owner_id=user_id,
                bank=BankSource.MONOBANK,
                amount=amount_val,
                currency="UAH",
                balance_after=Decimal("900.00"),
                transaction_currency="UAH",
                transaction_amount=amount_val,
                # Stagger the dates so the .order_by(desc) is completely deterministic
                date=base_time - timedelta(days=i),
                balance_currency="UAH",
                hash_id=f"hash_page_{user_id}_{i}_{uuid.uuid4()}"
            )
            transactions.append(tx)

        db.add_all(transactions)
        await db.commit()

    # Query Page 1: The mathematical boundary holds at 50
    resp_page_1 = await client.get("/api/transactions?limit=50&offset=0")
    assert resp_page_1.status_code == 200
    data_page_1 = resp_page_1.json()
    assert len(data_page_1) == 50
    # Proves the most recent transaction (i=0) was loaded first
    assert data_page_1[0]["amount"] == "-1.00"

    # Query Page 2: The offset correctly shifts the window
    resp_page_2 = await client.get("/api/transactions?limit=50&offset=50")
    assert resp_page_2.status_code == 200
    data_page_2 = resp_page_2.json()
    assert len(data_page_2) == 50
    # Proves the exact starting point of the next block (i=50)
    assert data_page_2[0]["amount"] == "-51.00"

    # Query Page 3: Out of bounds returns an empty array, not a crash
    resp_page_3 = await client.get("/api/transactions?limit=50&offset=100")
    assert resp_page_3.status_code == 200
    assert len(resp_page_3.json()) == 0