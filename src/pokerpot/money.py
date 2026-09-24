"""Parsing and formatting of money, always as integer cents."""

from __future__ import annotations

import re

from pokerpot.errors import ValidationError

_MONEY_RE = re.compile(r"^\$?\s*(\d{1,12})(?:\.(\d{1,2}))?$")


def parse_money(text: str) -> int:
    """Parse a human amount such as ``20``, ``20.5`` or ``$20.50`` into cents."""
    match = _MONEY_RE.match(text.strip())
    if match is None:
        raise ValidationError(
            f"Invalid amount {text!r}; use a positive amount such as 20 or 20.50."
        )
    whole, fraction = match.group(1), match.group(2) or ""
    cents = int(whole) * 100 + int(fraction.ljust(2, "0"))
    if cents <= 0:
        raise ValidationError("Amount must be greater than zero.")
    return cents


def format_money(cents: int, *, plus: bool = False) -> str:
    """Format cents as ``$20.50`` (or ``-$20.50`` / ``+$20.50``)."""
    sign = "-" if cents < 0 else ("+" if plus else "")
    value = abs(cents)
    return f"{sign}${value // 100}.{value % 100:02d}"
