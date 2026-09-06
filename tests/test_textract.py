import json
from pathlib import Path
from typing import Any, cast

import pytest
from botocore.client import BaseClient
from botocore.exceptions import ClientError

from expense_intelligence.ocr.textract import TextractOcrProvider, parse_expense_response
from expense_intelligence.ocr.types import OcrProviderError, TransientOcrError


def response_fixture() -> dict[str, Any]:
    return json.loads(Path("tests/fixtures/textract_response.json").read_text(encoding="utf-8"))


def test_textract_response_is_normalized_with_evidence() -> None:
    extraction = parse_expense_response(response_fixture())

    assert extraction.provider == "amazon-textract"
    assert extraction.receipt.merchant == "Beispielmarkt Berlin"
    assert str(extraction.receipt.total) == "12.34"
    assert len(extraction.receipt.line_items) == 2
    assert extraction.receipt.line_items[0].description == "KAFFEE"
    assert extraction.receipt.evidence[0].bounding_box is not None
    assert "ResponseMetadata" not in extraction.raw


def test_textract_response_requires_critical_fields() -> None:
    with pytest.raises(OcrProviderError, match="no expense document"):
        parse_expense_response({})

    response = response_fixture()
    response["ExpenseDocuments"][0]["SummaryFields"] = []
    with pytest.raises(OcrProviderError, match="VENDOR_NAME"):
        parse_expense_response(response)


class StubTextractClient:
    def __init__(
        self, response: dict[str, Any] | None = None, error_code: str | None = None
    ) -> None:
        self.response = response
        self.error_code = error_code

    def analyze_expense(self, **_: object) -> dict[str, Any]:
        if self.error_code:
            raise ClientError(
                {"Error": {"Code": self.error_code, "Message": "provider error"}},
                "AnalyzeExpense",
            )
        assert self.response is not None
        return self.response


def test_textract_provider_classifies_transient_errors() -> None:
    provider = TextractOcrProvider(
        "eu-central-1",
        cast(BaseClient, StubTextractClient(error_code="ThrottlingException")),
    )
    with pytest.raises(TransientOcrError):
        provider.extract(b"image")


def test_textract_provider_parses_success() -> None:
    provider = TextractOcrProvider(
        "eu-central-1",
        cast(BaseClient, StubTextractClient(response_fixture())),
    )
    assert provider.extract(b"image").receipt.currency == "EUR"
