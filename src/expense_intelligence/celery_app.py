from celery import Celery

from expense_intelligence.config import get_settings

settings = get_settings()

celery_app = Celery(
    "expense_intelligence",
    broker=settings.redis_url,
    include=["expense_intelligence.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_backend=None,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)
