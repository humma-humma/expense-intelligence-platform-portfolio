from datetime import date
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    left: float
    top: float
    width: float
    height: float


class OcrEvidence(BaseModel):
    field_type: str
    text: str
    confidence: Decimal = Field(ge=0, le=100)
    page: int = Field(default=1, ge=1)
    bounding_box: BoundingBox | None = None


class OcrLineItem(BaseModel):
    description: str
    total: Decimal
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    confidence: Decimal = Field(ge=0, le=100)
    evidence: list[OcrEvidence] = Field(default_factory=list)


class OcrReceipt(BaseModel):
    merchant: str
    purchase_date: date
    total: Decimal
    currency: str = "EUR"
    confidence: Decimal = Field(ge=0, le=100)
    line_items: list[OcrLineItem] = Field(default_factory=list)
    evidence: list[OcrEvidence] = Field(default_factory=list)


class OcrExtraction(BaseModel):
    provider: str
    provider_version: str | None = None
    receipt: OcrReceipt
    raw: dict[str, object]


class OcrProvider(Protocol):
    def extract(self, image_bytes: bytes) -> OcrExtraction: ...


class OcrProviderError(Exception):
    pass


class TransientOcrError(OcrProviderError):
    pass
