import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from arq import create_pool

from app.database import engine, Base
from app.routers import transaction, user, google_auth, rules
from app.models.transaction import Transaction
from app.models.user import User
from app.core.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis_pool = await create_pool(settings.redis_settings)
    yield
    await app.state.redis_pool.close()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    return {"status": "ok"}


app.include_router(transaction.router)
app.include_router(user.router)
app.include_router(google_auth.router)
app.include_router(rules.router)
