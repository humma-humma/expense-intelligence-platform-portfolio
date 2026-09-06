from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from uuid import UUID

import redis
from fastapi import FastAPI, HTTPException, Request, status
from sqlalchemy import Engine, text
from sqlalchemy.orm import Session, sessionmaker

from expense_intelligence.api.receipts import router as receipts_router
from expense_intelligence.config import Settings, get_settings
from expense_intelligence.database import make_engine, make_session_factory
from expense_intelligence.storage import ArtifactStorage, S3ArtifactStorage
from expense_intelligence.tasks import dispatch_receipt_job


def create_app(
    settings: Settings | None = None,
    *,
    engine: Engine | None = None,
    storage: ArtifactStorage | None = None,
    dispatch_job: Callable[[UUID], None] = dispatch_receipt_job,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    resolved_engine = engine or make_engine(resolved_settings.database_url)
    resolved_storage = storage or S3ArtifactStorage(resolved_settings)
    session_factory = make_session_factory(resolved_engine)
    redis_client = redis.Redis.from_url(resolved_settings.redis_url)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        resolved_storage.ensure_bucket()
        yield
        resolved_engine.dispose()
        redis_client.close()

    application = FastAPI(
        title=resolved_settings.app_name,
        version="0.1.0",
        description="Personal German receipt ingestion and expense intelligence service.",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.engine = resolved_engine
    application.state.session_factory = session_factory
    application.state.storage = resolved_storage
    application.state.dispatch_job = dispatch_job
    application.state.redis = redis_client
    application.include_router(receipts_router)

    @application.get("/health/live", tags=["health"])
    async def liveness() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "expense-intelligence",
            "environment": resolved_settings.environment,
        }

    @application.get("/health/ready", tags=["health"])
    def readiness(request: Request) -> dict[str, str]:
        try:
            factory: sessionmaker[Session] = request.app.state.session_factory
            with factory() as session:
                session.execute(text("SELECT 1"))
            request.app.state.redis.ping()
            request.app.state.storage.check()
        except Exception as error:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "A required dependency is unavailable"
            ) from error
        return {"status": "ready"}

    return application


app = create_app()
