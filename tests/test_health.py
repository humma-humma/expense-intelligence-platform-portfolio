import asyncio
from typing import cast

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


def test_liveness_reports_service_and_environment(app: FastAPI) -> None:

    async def request_liveness() -> dict[str, str]:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/live")
        assert response.status_code == 200
        return cast(dict[str, str], response.json())

    assert asyncio.run(request_liveness()) == {
        "status": "ok",
        "service": "expense-intelligence",
        "environment": "test",
    }


def test_readiness_checks_dependencies(app: FastAPI) -> None:
    async def request_readiness() -> int:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
        return response.status_code

    assert asyncio.run(request_readiness()) == 200


def test_readiness_fails_when_storage_is_unhealthy(app: FastAPI) -> None:
    app.state.storage.healthy = False

    async def request_readiness() -> int:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
        return response.status_code

    assert asyncio.run(request_readiness()) == 503


def test_lifespan_initializes_and_closes_dependencies(app: FastAPI) -> None:
    async def run_lifespan() -> None:
        async with app.router.lifespan_context(app):
            pass

    asyncio.run(run_lifespan())
