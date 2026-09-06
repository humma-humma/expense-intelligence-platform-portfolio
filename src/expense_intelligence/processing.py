import json
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_intelligence.models import (
    JobStatus,
    OcrObservation,
    Receipt,
    ReceiptItem,
    ReceiptJob,
)
from expense_intelligence.ocr.types import OcrEvidence, OcrProvider
from expense_intelligence.storage import ArtifactStorage


class JobNotFoundError(Exception):
    pass


def _observation(
    receipt_id: UUID,
    evidence: OcrEvidence,
    receipt_item_id: UUID | None = None,
) -> OcrObservation:
    return OcrObservation(
        receipt_id=receipt_id,
        receipt_item_id=receipt_item_id,
        field_type=evidence.field_type,
        raw_text=evidence.text,
        confidence=evidence.confidence,
        page=evidence.page,
        bounding_box=evidence.bounding_box.model_dump() if evidence.bounding_box else None,
    )


def _validation_warnings(
    total: Decimal, item_total: Decimal, confidence: Decimal, threshold: Decimal
) -> list[str]:
    warnings = []
    if confidence < threshold:
        warnings.append("critical_field_confidence_below_threshold")
    if item_total and abs(item_total - total) > Decimal("0.02"):
        warnings.append("line_item_total_mismatch")
    return warnings


def process_receipt_job(
    session: Session,
    job_id: UUID,
    storage: ArtifactStorage,
    provider: OcrProvider,
    review_threshold: Decimal,
) -> None:
    job = session.get(ReceiptJob, job_id)
    if job is None:
        raise JobNotFoundError(str(job_id))
    if job.status in {JobStatus.CONFIRMED, JobStatus.NEEDS_REVIEW}:
        return

    job.status = JobStatus.PROCESSING
    job.attempts += 1
    session.commit()

    image_bytes = storage.get(job.object_key)
    extraction = provider.extract(image_bytes)
    raw_key = f"ocr/{job.id}.json"
    storage.put(
        raw_key,
        json.dumps(extraction.raw, ensure_ascii=False).encode("utf-8"),
        "application/json",
    )

    existing_receipt = session.scalar(select(Receipt).where(Receipt.job_id == job.id))
    if existing_receipt is not None:
        return

    parsed = extraction.receipt
    item_total = sum((item.total for item in parsed.line_items), start=Decimal(0))
    warnings = _validation_warnings(
        parsed.total,
        item_total,
        parsed.confidence,
        review_threshold,
    )
    receipt = Receipt(
        job_id=job.id,
        merchant=parsed.merchant,
        purchase_date=parsed.purchase_date,
        total=parsed.total,
        currency=parsed.currency,
        confidence=parsed.confidence,
        provider=extraction.provider,
        provider_version=extraction.provider_version,
        validation_warnings=warnings,
        raw_result=parsed.model_dump(mode="json"),
    )
    session.add(receipt)
    session.flush()
    session.add_all(_observation(receipt.id, evidence) for evidence in parsed.evidence)

    for parsed_item in parsed.line_items:
        item = ReceiptItem(
            receipt_id=receipt.id,
            description=parsed_item.description,
            quantity=parsed_item.quantity,
            unit_price=parsed_item.unit_price,
            total=parsed_item.total,
            confidence=parsed_item.confidence,
        )
        session.add(item)
        session.flush()
        session.add_all(
            _observation(receipt.id, evidence, item.id) for evidence in parsed_item.evidence
        )

    job.ocr_result_key = raw_key
    job.status = JobStatus.NEEDS_REVIEW if warnings else JobStatus.CONFIRMED
    job.error_code = None
    job.error_message = None
    session.commit()


def mark_job_failed(session: Session, job_id: UUID, code: str, message: str) -> None:
    session.rollback()
    job = session.get(ReceiptJob, job_id)
    if job is None:
        return
    job.status = JobStatus.FAILED
    job.error_code = code
    job.error_message = message[:1000]
    session.commit()


def mark_job_retrying(session: Session, job_id: UUID, message: str) -> None:
    session.rollback()
    job = session.get(ReceiptJob, job_id)
    if job is None:
        return
    job.status = JobStatus.RETRYING
    job.error_code = "TRANSIENT_PROCESSING_ERROR"
    job.error_message = message[:1000]
    session.commit()
