import asyncio
from decimal import Decimal
from io import BytesIO
from typing import cast
from uuid import UUID

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient, Response
from PIL import Image
from sqlalchemy import Engine

from expense_intelligence.database import make_session_factory
from expense_intelligence.ocr.fake import FakeOcrProvider
from expense_intelligence.processing import process_receipt_job
from expense_intelligence.storage import ArtifactStorage


def png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="PNG")
    return buffer.getvalue()


async def request(app: FastAPI, method: str, path: str, **kwargs: object) -> Response:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def test_receipt_moves_from_upload_to_fake_ocr_result(
    app: FastAPI,
    engine: Engine,
    storage: ArtifactStorage,
    dispatched_jobs: list[UUID],
) -> None:
    upload = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("receipt.png", png_bytes(), "image/png")},
            headers={"Idempotency-Key": "upload-1"},
        )
    )

    assert upload.status_code == 202
    job_id = UUID(cast(dict[str, object], upload.json())["id"])
    assert dispatched_jobs == [job_id]

    with make_session_factory(engine)() as session:
        process_receipt_job(session, job_id, storage, FakeOcrProvider(), Decimal("80"))

    job = asyncio.run(request(app, "GET", f"/api/v1/jobs/{job_id}"))
    result = asyncio.run(request(app, "GET", f"/api/v1/jobs/{job_id}/result"))

    assert job.json()["status"] == "CONFIRMED"
    assert result.status_code == 200
    assert result.json()["merchant"] == "Beispielmarkt Berlin"
    assert result.json()["total"] == "12.34"
    assert result.json()["line_items"][0]["description"] == "Beispielprodukt"


def test_duplicate_image_returns_existing_job(app: FastAPI, dispatched_jobs: list[UUID]) -> None:
    first = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("first.png", png_bytes(), "image/png")},
        )
    )
    second = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("second.png", png_bytes(), "image/png")},
        )
    )

    assert second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert len(dispatched_jobs) == 1


def test_idempotency_key_cannot_be_reused_for_another_image(app: FastAPI) -> None:
    first = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("first.png", png_bytes(), "image/png")},
            headers={"Idempotency-Key": "one-request"},
        )
    )
    second = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("second.jpg", jpeg_bytes(), "image/jpeg")},
            headers={"Idempotency-Key": "one-request"},
        )
    )

    assert first.status_code == 202
    assert second.status_code == 409


def test_invalid_image_is_rejected(app: FastAPI) -> None:
    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("receipt.png", b"not an image", "image/png")},
        )
    )

    assert response.status_code == 422


def test_result_and_unknown_job_errors(app: FastAPI) -> None:
    upload = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("receipt.png", png_bytes(), "image/png")},
        )
    )
    job_id = upload.json()["id"]

    pending_result = asyncio.run(request(app, "GET", f"/api/v1/jobs/{job_id}/result"))
    missing_job = asyncio.run(request(app, "GET", f"/api/v1/jobs/{UUID(int=0)}"))
    missing_result = asyncio.run(request(app, "GET", f"/api/v1/jobs/{UUID(int=0)}/result"))

    assert pending_result.status_code == 409
    assert missing_job.status_code == 404
    assert missing_result.status_code == 404


def test_queue_failure_is_persisted(app: FastAPI) -> None:
    def fail_dispatch(_: UUID) -> None:
        raise ConnectionError("queue unavailable")

    app.state.dispatch_job = fail_dispatch
    response = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("new.jpg", jpeg_bytes(), "image/jpeg")},
        )
    )

    assert response.status_code == 503
    assert response.json()["detail"]["message"] == "The job was stored but could not be queued"


def jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (8, 8), "white").save(buffer, format="JPEG")
    return buffer.getvalue()


def test_image_validation_rejects_unsupported_and_mismatched_types(app: FastAPI) -> None:
    gif = BytesIO()
    Image.new("RGB", (8, 8), "white").save(gif, format="GIF")

    unsupported = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("receipt.gif", gif.getvalue(), "image/gif")},
        )
    )
    mismatched = asyncio.run(
        request(
            app,
            "POST",
            "/api/v1/receipts",
            files={"file": ("receipt.jpg", jpeg_bytes(), "image/png")},
        )
    )

    assert unsupported.status_code == 415
    assert mismatched.status_code == 415
