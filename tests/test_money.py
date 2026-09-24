from __future__ import annotations

import pytest

from poker.errors import ValidationError
from poker.money import format_money, parse_money


@pytest.mark.parametrize(
    ("text", "cents"),
    [
        ("20", 2000),
        ("20.5", 2050),
        ("20.50", 2050),
        ("$20.50", 2050),
        ("  $20.50  ", 2050),
        ("$ 3.50", 350),
        ("0.01", 1),
        ("123456", 12_345_600),
    ],
)
def test_parse_money(text: str, cents: int) -> None:
    assert parse_money(text) == cents


@pytest.mark.parametrize(
    "text",
    ["", "   ", "0", "0.00", "-5", "-0.01", "abc", "20.", ".5", "20.005", "$", "1e3", "20,50"],
)
def test_parse_money_rejects_invalid(text: str) -> None:
    with pytest.raises(ValidationError):
        parse_money(text)


def test_format_money() -> None:
    assert format_money(0) == "$0.00"
    assert format_money(1) == "$0.01"
    assert format_money(2050) == "$20.50"
    assert format_money(-2050) == "-$20.50"
    assert format_money(2050, plus=True) == "+$20.50"
    assert format_money(-2050, plus=True) == "-$20.50"
    assert format_money(0, plus=True) == "$0.00"
