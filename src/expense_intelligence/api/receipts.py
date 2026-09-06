import hashlib
from io import BytesIO
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile, status
from PIL import Image, UnidentifiedImageError
from sqlalchemy import select
from sqlalchemy.orm import Session

from expense_intelligence.api.schemas import JobResponse, ReceiptResultResponse
from expense_intelligence.config import Settings
from expense_intelligence.database import get_session
from expense_intelligence.models import JobStatus, Receipt, ReceiptItem, ReceiptJob
from expense_intelligence.storage import ArtifactStorage

router = APIRouter(prefix="/api/v1", tags=["receipts"])

SessionDependency = Annotated[Session, Depends(get_session)]

SUPPORTED_IMAGE_TYPES = {
    "JPEG": ("image/jpeg", ".jpg"),
    "PNG": ("image/png", ".png"),
}


def _validate_image(
    data: bytes, supplied_media_type: str | None, max_bytes: int
) -> tuple[str, str]:
    if not data:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "The uploaded file is empty")
    if len(data) > max_bytes:
        raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "The uploaded image is too large")

    try:
        with Image.open(BytesIO(data)) as image:
            image.verify()
            image_format = image.format
    except (UnidentifiedImageError, OSError) as error:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "The uploaded file is not a valid image"
        ) from error

    if image_format not in SUPPORTED_IMAGE_TYPES:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, "Only JPEG and PNG are supported"
        )
    detected_media_type, extension = SUPPORTED_IMAGE_TYPES[image_format]
    if supplied_media_type not in {detected_media_type, "application/octet-stream", None}:
        raise HTTPException(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "The declared content type does not match the image",
        )
    return detected_media_type, extension


@router.post("/receipts", response_model=JobResponse, status_code=status.HTTP_202_ACCEPTED)
def submit_receipt(
    request: Request,
    session: SessionDependency,
    file: Annotated[UploadFile, File(description="A single JPEG or PNG receipt image")],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", max_length=255)] = None,
) -> ReceiptJob:
    settings: Settings = request.app.state.settings
    data = file.file.read(settings.max_upload_bytes + 1)
    media_type, extension = _validate_image(data, file.content_type, settings.max_upload_bytes)
    content_hash = hashlib.sha256(data).hexdigest()

    if idempotency_key is not None:
        existing_for_key = session.scalar(
            select(ReceiptJob).where(ReceiptJob.idempotency_key == idempotency_key)
        )
        if existing_for_key is not None:
            if existing_for_key.content_hash != content_hash:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "The idempotency key was already used for a different image",
                )
            return existing_for_key

    existing = session.scalar(select(ReceiptJob).where(ReceiptJob.content_hash == content_hash))
    if existing is not None:
        return existing

    object_key = f"receipts/{content_hash[:2]}/{content_hash}{extension}"
    storage: ArtifactStorage = request.app.state.storage
    storage.put(object_key, data, media_type)

    job = ReceiptJob(
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
        content_hash=content_hash,
        original_filename=Path(file.filename or "receipt").name[:255],
        media_type=media_type,
        object_key=object_key,
    )
    session.add(job)
    session.commit()
    session.refresh(job)

    try:
        request.app.state.dispatch_job(job.id)
    except Exception as error:
        job.status = JobStatus.FAILED
        job.error_code = "QUEUE_UNAVAILABLE"
        job.error_message = "The background queue is unavailable"
        session.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            {"message": "The job was stored but could not be queued", "job_id": str(job.id)},
        ) from error

    return job


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: UUID, session: SessionDependency) -> ReceiptJob:
    job = session.get(ReceiptJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    return job


@router.get("/jobs/{job_id}/result", response_model=ReceiptResultResponse)
def get_result(job_id: UUID, session: SessionDependency) -> ReceiptResultResponse:
    job = session.get(ReceiptJob, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Job not found")
    receipt = session.scalar(select(Receipt).where(Receipt.job_id == job_id))
    if receipt is None:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Result is not ready: {job.status.value}")
    items = session.scalars(select(ReceiptItem).where(ReceiptItem.receipt_id == receipt.id)).all()
    return ReceiptResultResponse.model_validate(
        {
            "id": receipt.id,
            "job_id": receipt.job_id,
            "merchant": receipt.merchant,
            "purchase_date": receipt.purchase_date,
            "total": receipt.total,
            "currency": receipt.currency,
            "confidence": receipt.confidence,
            "provider": receipt.provider,
            "provider_version": receipt.provider_version,
            "validation_warnings": receipt.validation_warnings,
            "raw_result": receipt.raw_result,
            "line_items": items,
        }
    )
