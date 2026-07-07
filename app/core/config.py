import os
from sqlalchemy.ext.asyncio import create_async_engine
from pydantic_settings import BaseSettings, SettingsConfigDict
from arq.connections import RedisSettings


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str
    REDIS_URL: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"

    @property
    def cookie_secure(self):
        return self.is_production

    @property
    def cookie_samesite(self):
        return "lax"

    @property
    def redis_settings(self) -> RedisSettings:
        """Single source of truth for ARQ Redis connection parameters across App and Worker"""
        return RedisSettings(self.REDIS_URL)
    
    @property
    def db_engine_kwargs(self) -> dict:
        """Dynamically build the arg for SQLAlchemy engine kwargs"""
        kwargs = {
            "pool_pre_ping": True,
            "pool_recycle": 300,
            "pool_size": 5,
            "max_overflow": 10,
        }
        if self.is_production:
            kwargs["connect_args"] = {
                "ssl": "require",
                "server_settings": {
                    "statement_cache_size": "0"
                },
                "prepared_statement_cache_size": "0"
            }
        return kwargs


settings = Settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    **settings.db_engine_kwargs,
)
