"""Debt simplification from final session balances.

The greedy algorithm below is deterministic and produces a small number of
transfers, but it is not guaranteed to be globally minimal (finding a minimal
set of transfers is NP-hard in general). It is always derived from the final
balances and never from separately recorded debts.
"""

from __future__ import annotations

Transfer = tuple[int, int, int]  # (from_player_id, to_player_id, cents)


def settle(balances: dict[int, int]) -> list[Transfer]:
    """Return transfers that bring every non-zero balance to zero."""
    debtors = sorted(
        ((player_id, -net) for player_id, net in balances.items() if net < 0),
        key=lambda item: (-item[1], item[0]),
    )
    creditors = sorted(
        ((player_id, net) for player_id, net in balances.items() if net > 0),
        key=lambda item: (-item[1], item[0]),
    )
    transfers: list[Transfer] = []
    debtor_index = creditor_index = 0
    while debtor_index < len(debtors) and creditor_index < len(creditors):
        debtor_id, debt = debtors[debtor_index]
        creditor_id, credit = creditors[creditor_index]
        amount = min(debt, credit)
        transfers.append((debtor_id, creditor_id, amount))
        debt -= amount
        credit -= amount
        if debt == 0:
            debtor_index += 1
        else:
            debtors[debtor_index] = (debtor_id, debt)
        if credit == 0:
            creditor_index += 1
        else:
            creditors[creditor_index] = (creditor_id, credit)
    return transfers
