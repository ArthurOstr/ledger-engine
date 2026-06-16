import os
from sqlalchemy.ext.asyncio import create_async_engine
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    DATABASE_URL: str

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
    def db_engine_kwargs(self) -> dict:
        """Dynamically build the arg for SQLAlchemy engine kwargs"""
        kwargs = {"pool_pre_ping": True}
        if self.is_production:
            kwargs["connect_args"] = {"ssl": "require"}
        return kwargs


settings = Settings()

engine = create_async_engine(
    settings.DATABASE_URL,
    **settings.db_engine_kwargs,
)
