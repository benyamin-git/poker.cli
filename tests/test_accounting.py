from __future__ import annotations

import pytest

from poker.accounting import (
    equal_winner_amounts,
    round_net,
    session_balances,
    split_pot,
    validate_round,
)
from poker.errors import ValidationError


def test_split_pot_even() -> None:
    assert split_pot(5000, 2) == [2500, 2500]
    assert split_pot(1000, 1) == [1000]


def test_split_pot_remainder_goes_to_first_winners() -> None:
    assert split_pot(1000, 3) == [334, 333, 333]
    assert sum(split_pot(1000, 3)) == 1000
    assert split_pot(1001, 3) == [334, 334, 333]


def test_split_pot_requires_one_cent_per_winner() -> None:
    with pytest.raises(ValidationError):
        split_pot(1, 2)
    with pytest.raises(ValidationError):
        split_pot(2, 3)


def test_split_pot_requires_winners() -> None:
    with pytest.raises(ValidationError):
        split_pot(100, 0)


def test_equal_winner_amounts_preserves_entry_order() -> None:
    assert equal_winner_amounts(1000, [7, 3, 9]) == {7: 334, 3: 333, 9: 333}


def test_validate_round_accepts_balanced_round() -> None:
    validate_round({1: 2000, 2: 3000}, {3: 5000})


def test_validate_round_rejects_missing_sides() -> None:
    with pytest.raises(ValidationError, match="loser"):
        validate_round({}, {1: 100})
    with pytest.raises(ValidationError, match="winner"):
        validate_round({1: 100}, {})


def test_validate_round_rejects_overlap() -> None:
    with pytest.raises(ValidationError, match="both a loser and a winner"):
        validate_round({1: 100}, {1: 100})


def test_validate_round_rejects_non_positive_amounts() -> None:
    with pytest.raises(ValidationError, match="greater than zero"):
        validate_round({1: 0}, {2: 0})
    with pytest.raises(ValidationError, match="greater than zero"):
        validate_round({1: -100}, {2: -100})


def test_validate_round_rejects_imbalance() -> None:
    with pytest.raises(ValidationError, match="does not balance"):
        validate_round({1: 2000}, {2: 1000})


def test_round_net() -> None:
    assert round_net([(1, "loser", 2000), (2, "winner", 2000)]) == {1: -2000, 2: 2000}


def test_session_balances_sum_to_zero() -> None:
    balances = session_balances(
        [1, 2, 3],
        [
            [(1, "loser", 2000), (2, "winner", 2000)],
            [(2, "loser", 3000), (1, "winner", 1000), (3, "winner", 2000)],
        ],
    )
    assert balances == {1: -1000, 2: -1000, 3: 2000}
    assert sum(balances.values()) == 0
