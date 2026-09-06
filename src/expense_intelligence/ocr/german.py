import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from expense_intelligence.ocr.types import OcrProviderError

_CURRENCY_MARKERS = re.compile(r"(?:EUR|€)", re.IGNORECASE)
_SPACES = re.compile(r"[\s\u00a0]+")


def parse_german_money(value: str) -> Decimal:
    cleaned = _SPACES.sub("", _CURRENCY_MARKERS.sub("", value)).replace("'", "")
    if not cleaned:
        raise OcrProviderError(f"Invalid monetary value: {value!r}")

    if "," in cleaned:
        cleaned = cleaned.replace(".", "").replace(",", ".")
    elif cleaned.count(".") > 1:
        cleaned = cleaned.replace(".", "")

    try:
        return Decimal(cleaned)
    except InvalidOperation as error:
        raise OcrProviderError(f"Invalid monetary value: {value!r}") from error


def parse_german_date(value: str) -> date:
    normalized = value.strip()
    for date_format in ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(normalized, date_format).date()
        except ValueError:
            continue
    raise OcrProviderError(f"Invalid receipt date: {value!r}")
