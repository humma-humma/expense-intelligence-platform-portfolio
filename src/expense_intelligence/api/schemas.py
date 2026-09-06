from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from expense_intelligence.models import JobStatus


class JobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: JobStatus
    content_hash: str
    original_filename: str
    error_code: str | None
    error_message: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime


class ReceiptItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    description: str
    quantity: Decimal | None
    unit_price: Decimal | None
    total: Decimal
    confidence: Decimal


class ReceiptResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    job_id: UUID
    merchant: str
    purchase_date: date
    total: Decimal
    currency: str
    confidence: Decimal
    provider: str
    provider_version: str | None
    validation_warnings: list[str]
    raw_result: dict[str, object]
    line_items: list[ReceiptItemResponse]
