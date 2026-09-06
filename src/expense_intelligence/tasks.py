from uuid import UUID

from celery import Task

from expense_intelligence.celery_app import celery_app
from expense_intelligence.config import get_settings
from expense_intelligence.database import make_engine, make_session_factory
from expense_intelligence.ocr.provider import make_ocr_provider
from expense_intelligence.ocr.types import TransientOcrError
from expense_intelligence.processing import (
    mark_job_failed,
    mark_job_retrying,
    process_receipt_job,
)
from expense_intelligence.storage import S3ArtifactStorage

settings = get_settings()
session_factory = make_session_factory(make_engine(settings.database_url))
storage = S3ArtifactStorage(settings)
ocr_provider = make_ocr_provider(settings)


@celery_app.task(bind=True, max_retries=3, name="process_receipt")  # type: ignore[untyped-decorator]
def process_receipt(self: Task, job_id: str) -> None:
    parsed_job_id = UUID(job_id)
    with session_factory() as session:
        try:
            process_receipt_job(
                session,
                parsed_job_id,
                storage,
                ocr_provider,
                settings.ocr_review_threshold,
            )
        except TransientOcrError as error:
            mark_job_retrying(session, parsed_job_id, str(error))
            raise self.retry(exc=error, countdown=2 ** (self.request.retries + 1)) from error
        except Exception as error:
            mark_job_failed(session, parsed_job_id, "PROCESSING_ERROR", str(error))
            raise


def dispatch_receipt_job(job_id: UUID) -> None:
    process_receipt.delay(str(job_id))
