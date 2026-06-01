import pytest
import pytest_asyncio
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport, Response
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool
from sqlalchemy.future import select

from app.main import app
from app.database import get_db, engine, Base
from app.models.user import User

# --- DB SETUP ---
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


# --- TESTS: OAUTH GATEWAY ---

async def test_login_google_redirect():
    """Proves the endpoint correctly formats the URL and issues a 307 Redirect to Google."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/google_auth/google", follow_redirects=False)

    assert response.status_code == 307
    assert "accounts.google.com/o/oauth2/v2/auth" in response.headers["location"]
    assert "response_type=code" in response.headers["location"]


@patch("app.routers.google_auth.httpx")
async def test_google_callback_new_user(mock_httpx):
    """Proves a completely new email from Google results in a database entry and JWT cookie."""
    test_email = "new_google_user@example.com"

    # Isolate the mock context manager specifically to the router
    mock_client = AsyncMock()
    mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client

    mock_client.post.return_value = Response(
        200, json={"access_token": "mocked_google_token", "expires_in": 3599}
    )
    mock_client.get.return_value = Response(
        200, json={"email": test_email, "verified_email": True}
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/google_auth/google/callback?code=mock_auth_code",
            follow_redirects=False
        )

    # Verify redirection to the frontend success URI
    assert response.status_code == 307
    assert response.headers["location"] == "http://localhost:5173/"

    # Verify the internal system generated the JWT and HttpOnly cookie
    assert "access_token" in response.cookies

    # Verify the new user was forged in the database
    async with TestingSessionLocal() as db:
        result = await db.execute(select(User).where(User.email == test_email))
        user = result.scalars().first()
        assert user is not None
        assert user.email == test_email
        assert user.hashed_password == "GOOGLE_AUTH_NO_PASSWORD"


@patch("app.routers.google_auth.httpx")
async def test_google_callback_existing_user(mock_httpx):
    """Proves an existing user logging in via Google does not crash the unique constraint."""
    test_email = "existing_user@example.com"

    # Pre-forge the user in the database
    async with TestingSessionLocal() as db:
        existing_user = User(email=test_email, hashed_password="some_hashed_password")
        db.add(existing_user)
        await db.commit()

    # Isolate the mock
    mock_client = AsyncMock()
    mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client
    mock_client.post.return_value = Response(200, json={"access_token": "mocked_google_token"})
    mock_client.get.return_value = Response(200, json={"email": test_email})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get(
            "/api/google_auth/google/callback?code=mock_auth_code",
            follow_redirects=False
        )

    assert response.status_code == 307
    assert "access_token" in response.cookies

    # Verify no duplicate was created (database count should still be 1)
    async with TestingSessionLocal() as db:
        result = await db.execute(select(User))
        users = result.scalars().all()
        assert len(users) == 1


@patch("app.routers.google_auth.httpx")
async def test_google_callback_token_failure(mock_httpx):
    """Proves the system safely catches Google API failures without crashing."""

    mock_client = AsyncMock()
    mock_httpx.AsyncClient.return_value.__aenter__.return_value = mock_client
    mock_client.post.return_value = Response(400, json={"error": "invalid_grant"})

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/api/google_auth/google/callback?code=bad_code")

    assert response.status_code == 400
    assert response.json()["detail"] == "Failed to exchange token with Google"