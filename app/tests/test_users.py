import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.pool import NullPool

from app.main import app
from app.database import get_db, engine, Base



# Apply the interceptor to the application
app.dependency_overrides[get_db] = override_get_db

# Tell pytest to run these asynchronously
pytestmark = pytest.mark.asyncio


# --- SYSTEM HEALTH TESTS ---

async def test_health_check():
    async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --- REGISTRATION TESTS ---

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


# --- AUTHENTICATION & SESSION TESTS ---

async def test_login_user_success():
    test_email = f"login_{uuid.uuid4()}@example.com"
    test_password = "strongpassword123"

    async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Stage the user
        await ac.post(
            "/api/users/register",
            json={"email": test_email, "password": test_password},
        )

        # Execute login (Must use form data for OAuth2PasswordRequestForm)
        response = await ac.post(
            "/api/users/login",
            data={"username": test_email, "password": test_password},
        )

    assert response.status_code == 200
    assert response.json() == {"message": "Logged in successfully"}

    # Verify the HttpOnly cookie was set securely
    assert "access_token" in response.cookies
    cookie = response.cookies.get("access_token")
    assert cookie is not None


async def test_login_user_wrong_credentials():
    test_email = f"login_fail_{uuid.uuid4()}@example.com"
    test_password = "strongpassword123"

    async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await ac.post(
            "/api/users/register",
            json={"email": test_email, "password": test_password},
        )

        response = await ac.post(
            "/api/users/login",
            data={"username": test_email, "password": "wrongpassword"},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Incorrect email or password"
    assert "access_token" not in response.cookies


async def test_verify_session_authenticated():
    test_email = f"me_{uuid.uuid4()}@example.com"
    test_password = "strongpassword123"

    async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await ac.post(
            "/api/users/register",
            json={"email": test_email, "password": test_password},
        )

        await ac.post(
            "/api/users/login",
            data={"username": test_email, "password": test_password},
        )

        # The AsyncClient automatically handles the cookie set by the login
        response = await ac.get("/api/users/me")

    assert response.status_code == 200
    assert response.json() == {"email": test_email}


async def test_verify_session_unauthenticated():
    async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        # Attempt to access protected route without logging in
        response = await ac.get("/api/users/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Could not validate credentials"


async def test_logout_user():
    test_email = f"logout_{uuid.uuid4()}@example.com"
    test_password = "strongpassword123"

    async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        await ac.post(
            "/api/users/register",
            json={"email": test_email, "password": test_password},
        )

        await ac.post(
            "/api/users/login",
            data={"username": test_email, "password": test_password},
        )

        # Execute logout
        response = await ac.post("/api/users/logout")

        assert response.status_code == 200
        assert response.json() == {"message": "Logged out successfully"}

        # Verify session is destroyed by attempting to access protected route
        me_response = await ac.get("/api/users/me")
        assert me_response.status_code == 401