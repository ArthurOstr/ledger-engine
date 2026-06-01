import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from decimal import Decimal
from datetime import datetime

from app.main import app
from app.database import get_db, engine, Base
from app.routers.transaction import get_redis_pool
from app.models.transaction import Transaction, BankSource
from app.models.user import User

# --- DB SETUP ---
# Destroy connections after every query to guarantee clean test state
test_engine = create_async_engine(engine.url, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture(autouse=True)
async def prepare_database():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


app.dependency_overrides[get_db] = override_get_db


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
app.dependency_overrides[get_redis_pool] = override_get_redis_pool


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