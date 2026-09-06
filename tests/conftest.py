from collections.abc import Iterator
from dataclasses import dataclass, field
from uuid import UUID

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine, create_engine
from sqlalchemy.pool import StaticPool

from expense_intelligence.config import Settings
from expense_intelligence.main import create_app
from expense_intelligence.models import Base


@dataclass
class MemoryStorage:
    objects: dict[str, bytes] = field(default_factory=dict)
    healthy: bool = True

    def ensure_bucket(self) -> None:
        pass

    def put(self, key: str, data: bytes, content_type: str) -> None:
        self.objects[key] = data

    def get(self, key: str) -> bytes:
        return self.objects[key]

    def check(self) -> None:
        if not self.healthy:
            raise ConnectionError("storage unavailable")


class HealthyRedis:
    def ping(self) -> bool:
        return True

    def close(self) -> None:
        pass


@pytest.fixture
def engine() -> Iterator[Engine]:
    test_engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(test_engine)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def storage() -> MemoryStorage:
    return MemoryStorage()


@pytest.fixture
def dispatched_jobs() -> list[UUID]:
    return []


@pytest.fixture
def app(engine: Engine, storage: MemoryStorage, dispatched_jobs: list[UUID]) -> FastAPI:
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+pysqlite:///:memory:",
    )
    application = create_app(
        settings,
        engine=engine,
        storage=storage,
        dispatch_job=dispatched_jobs.append,
    )
    application.state.redis = HealthyRedis()
    return application
