import os
import pytest 
import pytest_asyncio
import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import NullPool
from alembic import command
from alembic.config import Config


from app.main import app
from app.database import get_db, Base 

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
if not TEST_DATABASE_URL:
    raise RuntimeError(
        "CRITICAL SECURITY BREACH: TEST_DATABASE_URL is not set."
        "Aborting test to save development data"
    )

test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestingSessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

@pytest_asyncio.fixture(autouse=True, scope="function")
async def prepare_database():
    """Builds and drops tables per test execution using Alembic to perfectly mirror production on the test engine"""
    alembic_cfg = Config("alembic.ini")

    alembic_cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    try:
        await asyncio.to_thread(
        command.upgrade, alembic_cfg, "head")
        yield

    finally:
        await asyncio.to_thread(command.downgrade, alembic_cfg, "base")

@pytest.fixture(autouse=True)
def override_fastapi_dependecies():
    """Injects the testing session into the FastAPI application router"""
    async def _override_db():
        async with TestingSessionLocal() as session:
            yield session 

    app.dependency_overrides[get_db] = _override_db 
    yield 
    app.dependency_overrides.clear()
