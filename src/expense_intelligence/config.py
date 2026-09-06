from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated process settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="EXPENSE_",
        extra="ignore",
    )

    app_name: str = "Expense Intelligence Platform"
    environment: Literal["development", "test", "staging", "production"] = "development"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    monthly_budget_target_eur: Decimal = Field(default=Decimal("15"), ge=0)
    monthly_budget_alert_eur: Decimal = Field(default=Decimal("25"), ge=0)
    database_url: str = "postgresql+psycopg://expense:expense@localhost:5432/expense"
    redis_url: str = "redis://localhost:6379/0"
    s3_endpoint_url: str | None = "http://localhost:9000"
    s3_access_key: str = "expense-local"
    s3_secret_key: str = "expense-local-secret"
    s3_bucket: str = "receipts"
    s3_region: str = "eu-central-1"
    s3_server_side_encryption: bool = False
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    ocr_provider: Literal["fake", "textract"] = "fake"
    ocr_review_threshold: Decimal = Field(default=Decimal("80"), ge=0, le=100)


@lru_cache
def get_settings() -> Settings:
    return Settings()
