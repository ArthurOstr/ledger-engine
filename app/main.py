from contextlib import asynccontextmanager
from fastapi import FastAPI

from app.database import engine, Base
from app.models.transaction import Transaction

from app.routers import transaction


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    yield


app = FastAPI(lifespan=lifespan)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


app.include_router(transaction.router)
