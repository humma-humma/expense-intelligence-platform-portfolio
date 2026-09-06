from decimal import Decimal

import pytest
from pydantic import ValidationError

from expense_intelligence.config import Settings


def test_settings_have_cost_safe_defaults() -> None:
    settings = Settings(_env_file=None)

    assert settings.environment == "development"
    assert settings.monthly_budget_target_eur == Decimal("15")
    assert settings.monthly_budget_alert_eur == Decimal("25")


def test_settings_reject_negative_budget() -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None, monthly_budget_target_eur=Decimal("-1"))
