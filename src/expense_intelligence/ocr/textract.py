from decimal import Decimal
from typing import Any

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from expense_intelligence.ocr.german import parse_german_date, parse_german_money
from expense_intelligence.ocr.types import (
    BoundingBox,
    OcrEvidence,
    OcrExtraction,
    OcrLineItem,
    OcrProviderError,
    OcrReceipt,
    TransientOcrError,
)

_TRANSIENT_CODES = {
    "InternalServerError",
    "ProvisionedThroughputExceededException",
    "ThrottlingException",
}


def _evidence(field: dict[str, Any]) -> OcrEvidence | None:
    value = field.get("ValueDetection")
    if not isinstance(value, dict) or not value.get("Text"):
        return None
    raw_box = value.get("Geometry", {}).get("BoundingBox")
    box = None
    if isinstance(raw_box, dict):
        box = BoundingBox(
            left=float(raw_box.get("Left", 0)),
            top=float(raw_box.get("Top", 0)),
            width=float(raw_box.get("Width", 0)),
            height=float(raw_box.get("Height", 0)),
        )
    return OcrEvidence(
        field_type=str(field.get("Type", {}).get("Text", "OTHER")),
        text=str(value["Text"]),
        confidence=Decimal(str(value.get("Confidence", 0))),
        page=int(field.get("PageNumber", 1)),
        bounding_box=box,
    )


def _field_map(fields: list[dict[str, Any]]) -> dict[str, OcrEvidence]:
    result: dict[str, OcrEvidence] = {}
    for field in fields:
        item = _evidence(field)
        if item is not None:
            result[item.field_type] = item
    return result


def _parse_line_items(document: dict[str, Any]) -> list[OcrLineItem]:
    parsed: list[OcrLineItem] = []
    for group in document.get("LineItemGroups", []):
        for line in group.get("LineItems", []):
            fields = _field_map(line.get("LineItemExpenseFields", []))
            description = fields.get("ITEM") or fields.get("ITEM_NAME")
            total = fields.get("PRICE")
            if description is None or total is None:
                continue
            quantity = fields.get("QUANTITY")
            unit_price = fields.get("UNIT_PRICE")
            evidence = list(fields.values())
            parsed.append(
                OcrLineItem(
                    description=description.text,
                    total=parse_german_money(total.text),
                    quantity=parse_german_money(quantity.text) if quantity else None,
                    unit_price=parse_german_money(unit_price.text) if unit_price else None,
                    confidence=min(item.confidence for item in evidence),
                    evidence=evidence,
                )
            )
    return parsed


def parse_expense_response(response: dict[str, Any]) -> OcrExtraction:
    documents = response.get("ExpenseDocuments", [])
    if not documents:
        raise OcrProviderError("Textract returned no expense document")
    document = documents[0]
    summary = _field_map(document.get("SummaryFields", []))
    try:
        merchant = summary["VENDOR_NAME"]
        receipt_date = summary["INVOICE_RECEIPT_DATE"]
        total = summary["TOTAL"]
    except KeyError as error:
        raise OcrProviderError(f"Missing required Textract field: {error.args[0]}") from error

    critical = [merchant, receipt_date, total]
    sanitized_raw = {key: value for key, value in response.items() if key != "ResponseMetadata"}
    return OcrExtraction(
        provider="amazon-textract",
        provider_version=response.get("AnalyzeExpenseModelVersion"),
        receipt=OcrReceipt(
            merchant=merchant.text,
            purchase_date=parse_german_date(receipt_date.text),
            total=parse_german_money(total.text),
            currency="EUR",
            confidence=min(item.confidence for item in critical),
            line_items=_parse_line_items(document),
            evidence=list(summary.values()),
        ),
        raw=sanitized_raw,
    )


class TextractOcrProvider:
    def __init__(self, region: str, client: BaseClient | None = None) -> None:
        self.client: BaseClient = client or boto3.client("textract", region_name=region)

    def extract(self, image_bytes: bytes) -> OcrExtraction:
        try:
            response = self.client.analyze_expense(Document={"Bytes": image_bytes})
        except ClientError as error:
            code = error.response.get("Error", {}).get("Code", "TextractError")
            if code in _TRANSIENT_CODES:
                raise TransientOcrError(str(error)) from error
            raise OcrProviderError(str(error)) from error
        except BotoCoreError as error:
            raise TransientOcrError(str(error)) from error
        return parse_expense_response(response)
