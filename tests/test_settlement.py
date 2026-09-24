from __future__ import annotations

from poker.settlement import settle


def test_settle_empty() -> None:
    assert settle({}) == []
    assert settle({1: 0, 2: 0}) == []


def test_settle_single_debtor_single_creditor() -> None:
    assert settle({1: -2000, 2: 2000}) == [(1, 2, 2000)]


def test_settle_one_debtor_two_creditors() -> None:
    assert settle({1: -8000, 2: 4500, 3: 3500}) == [(1, 2, 4500), (1, 3, 3500)]


def test_settle_two_debtors_one_creditor() -> None:
    assert settle({1: -1000, 2: -2000, 3: 3000}) == [(2, 3, 2000), (1, 3, 1000)]


def test_settle_mixed() -> None:
    transfers = settle({1: -5000, 2: -3000, 3: 4000, 4: 4000})
    assert transfers == [(1, 3, 4000), (1, 4, 1000), (2, 4, 3000)]


def test_settle_ties_are_deterministic() -> None:
    first = settle({5: -1000, 1: 500, 2: 500})
    second = settle({2: 500, 5: -1000, 1: 500})
    assert first == second == [(5, 1, 500), (5, 2, 500)]


def test_settle_transfers_clear_all_balances() -> None:
    balances = {1: -7300, 2: -1900, 3: 4500, 4: 2500, 5: 2200, 6: 0}
    for from_id, to_id, amount in settle(balances):
        balances[from_id] += amount
        balances[to_id] -= amount
    assert all(balance == 0 for balance in balances.values())


def test_settle_total_matches_debt_and_credit() -> None:
    balances = {1: -8000, 2: 3000, 3: 5000}
    transfers = settle(balances)
    assert sum(amount for _, _, amount in transfers) == 8000
