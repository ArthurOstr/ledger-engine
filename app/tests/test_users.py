import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import get_db, engine

# Create a special test engine that destroys connections after every query
test_engine = create_async_engine(engine.url, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(
    autocommit=False, autoflush=False, bind=test_engine
)


# Intercept FastAPI's database request and hand it our safe test engine
async def override_get_db():
    async with TestingSessionLocal() as session:
        yield session


# Apply the interceptor to the application
app.dependency_overrides[get_db] = override_get_db

# Tell pytest to run these asynchronously
pytestmark = pytest.mark.asyncio


async def test_register_user_success():
    test_email = f"test_{uuid.uuid4()}@example.com"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.post(
            "/api/users/register",
            json={"email": test_email, "password": "strongpassword123"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["email"] == test_email
    assert "id" in data


async def test_register_user_duplicate():
    test_email = f"duplicate_{uuid.uuid4()}@example.com"

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Register first time
        await ac.post(
            "/api/users/register",
            json={"email": test_email, "password": "strongpassword123"},
        )

        # Try to breach the airlock
        response = await ac.post(
            "/api/users/register",
            json={"email": test_email, "password": "strongpassword123"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Email already registered"
