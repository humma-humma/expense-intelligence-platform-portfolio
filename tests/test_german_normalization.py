from datetime import date
from decimal import Decimal

import pytest

from expense_intelligence.ocr.german import parse_german_date, parse_german_money
from expense_intelligence.ocr.types import OcrProviderError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12,34 €", Decimal("12.34")),
        ("1.234,56 EUR", Decimal("1234.56")),
        ("-1,00", Decimal("-1.00")),
        ("2.50", Decimal("2.50")),
    ],
)
def test_parse_german_money(raw: str, expected: Decimal) -> None:
    assert parse_german_money(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("30.08.2026", date(2026, 8, 30)),
        ("30.08.26", date(2026, 8, 30)),
        ("2026-08-30", date(2026, 8, 30)),
    ],
)
def test_parse_german_date(raw: str, expected: date) -> None:
    assert parse_german_date(raw) == expected


def test_invalid_localized_values_fail() -> None:
    with pytest.raises(OcrProviderError):
        parse_german_money("EUR")
    with pytest.raises(OcrProviderError):
        parse_german_date("not-a-date")
