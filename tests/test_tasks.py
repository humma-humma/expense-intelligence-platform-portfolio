from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID

from sqlalchemy import Engine

from expense_intelligence import tasks
from expense_intelligence.database import make_session_factory
from expense_intelligence.models import JobStatus, ReceiptJob
from expense_intelligence.ocr.fake import FakeOcrProvider
from expense_intelligence.storage import ArtifactStorage


def test_dispatch_sends_job_to_celery() -> None:
    delay = Mock()
    tasks.process_receipt.delay = delay
    job_id = UUID(int=1)

    tasks.dispatch_receipt_job(job_id)

    delay.assert_called_once_with(str(job_id))


def test_task_processes_job(engine: Engine, storage: ArtifactStorage) -> None:
    with make_session_factory(engine)() as session:
        job = ReceiptJob(
            status=JobStatus.QUEUED,
            content_hash="b" * 64,
            original_filename="receipt.png",
            media_type="image/png",
            object_key="receipts/bb/receipt.png",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        session.add(job)
        session.commit()
        job_id = job.id
    storage.put("receipts/bb/receipt.png", b"image", "image/png")
    tasks.session_factory = make_session_factory(engine)
    tasks.storage = storage
    tasks.ocr_provider = FakeOcrProvider()

    tasks.process_receipt.run(str(job_id))
