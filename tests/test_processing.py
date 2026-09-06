from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, select

from expense_intelligence.database import make_session_factory
from expense_intelligence.models import JobStatus, ReceiptItem, ReceiptJob
from expense_intelligence.ocr.fake import FakeOcrProvider
from expense_intelligence.ocr.types import OcrExtraction, TransientOcrError
from expense_intelligence.processing import (
    JobNotFoundError,
    mark_job_failed,
    mark_job_retrying,
    process_receipt_job,
)
from expense_intelligence.storage import ArtifactStorage


def add_job(engine: Engine, storage: ArtifactStorage, content_hash: str = "a" * 64) -> UUID:
    object_key = f"receipts/{content_hash[:2]}/receipt.png"
    storage.put(object_key, b"image", "image/png")
    with make_session_factory(engine)() as session:
        job = ReceiptJob(
            status=JobStatus.QUEUED,
            content_hash=content_hash,
            original_filename="receipt.png",
            media_type="image/png",
            object_key=object_key,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(job)
        session.commit()
        return job.id


def test_transient_failure_can_be_recorded_for_retry(
    engine: Engine, storage: ArtifactStorage
) -> None:
    job_id = add_job(engine, storage)

    class TransientProvider:
        def extract(self, image_bytes: bytes) -> OcrExtraction:
            raise TransientOcrError("temporary provider failure")

    with make_session_factory(engine)() as session:
        try:
            process_receipt_job(session, job_id, storage, TransientProvider(), Decimal("80"))
        except TransientOcrError as error:
            mark_job_retrying(session, job_id, str(error))

        job = session.get(ReceiptJob, job_id)
        assert job is not None
        assert job.status == JobStatus.RETRYING
        assert job.attempts == 1
        assert job.error_code == "TRANSIENT_PROCESSING_ERROR"


def test_processing_persists_items_and_is_idempotent(
    engine: Engine, storage: ArtifactStorage
) -> None:
    job_id = add_job(engine, storage)
    with make_session_factory(engine)() as session:
        process_receipt_job(session, job_id, storage, FakeOcrProvider(), Decimal("80"))
        process_receipt_job(session, job_id, storage, FakeOcrProvider(), Decimal("80"))

        items = session.scalars(select(ReceiptItem)).all()
        job = session.get(ReceiptJob, job_id)
        assert job is not None
        assert job.status == JobStatus.CONFIRMED
        assert job.ocr_result_key == f"ocr/{job_id}.json"
        assert len(items) == 1

        try:
            process_receipt_job(session, UUID(int=0), storage, FakeOcrProvider(), Decimal("80"))
        except JobNotFoundError:
            pass
        else:
            raise AssertionError("Missing jobs must fail")


def test_permanent_failure_is_recorded(engine: Engine, storage: ArtifactStorage) -> None:
    job_id = add_job(engine, storage)
    with make_session_factory(engine)() as session:
        mark_job_failed(session, job_id, "BROKEN", "permanent failure")
        mark_job_failed(session, UUID(int=0), "IGNORED", "missing job")

        job = session.get(ReceiptJob, job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED
        assert job.error_code == "BROKEN"
