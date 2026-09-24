"""Pure accounting engine: pot splitting, round validation and balances.

This module never touches the database or the CLI so it can be tested on its
own. All amounts are integer cents.
"""

from __future__ import annotations

from collections.abc import Iterable

from poker.errors import ValidationError
from poker.money import format_money

Participant = tuple[int, str, int]  # (player_id, role, amount_cents)


def split_pot(pot_cents: int, winners: int) -> list[int]:
    """Split a pot equally between winners.

    The remainder is distributed one extra cent at a time to the first winners
    in the order they were entered, so the split is deterministic and the
    shares always add up to the pot exactly.
    """
    if winners <= 0:
        raise ValidationError("A round needs at least one winner.")
    if pot_cents < winners:
        raise ValidationError(
            f"The pot ({format_money(pot_cents)}) must be at least 1 cent per winner."
        )
    share, remainder = divmod(pot_cents, winners)
    return [share + (1 if index < remainder else 0) for index in range(winners)]


def equal_winner_amounts(pot_cents: int, winner_ids: list[int]) -> dict[int, int]:
    """Return the equal split of a pot keyed by player ID, in entry order."""
    return dict(zip(winner_ids, split_pot(pot_cents, len(winner_ids)), strict=True))


def validate_round(loser_amounts: dict[int, int], winner_amounts: dict[int, int]) -> None:
    """Validate one round; raise ``ValidationError`` when it does not balance."""
    if not loser_amounts:
        raise ValidationError("A round needs at least one loser.")
    if not winner_amounts:
        raise ValidationError("A round needs at least one winner.")
    overlap = set(loser_amounts) & set(winner_amounts)
    if overlap:
        raise ValidationError("A player cannot be both a loser and a winner in the same round.")
    for amount in (*loser_amounts.values(), *winner_amounts.values()):
        if amount <= 0:
            raise ValidationError("Amounts must be greater than zero.")
    total_losses = sum(loser_amounts.values())
    total_wins = sum(winner_amounts.values())
    if total_losses != total_wins:
        raise ValidationError(
            f"The round does not balance: losers put in {format_money(total_losses)} "
            f"but winners receive {format_money(total_wins)}."
        )


def round_net(participants: Iterable[Participant]) -> dict[int, int]:
    """Compute each player's net cents for one round."""
    net: dict[int, int] = {}
    for player_id, role, amount in participants:
        sign = 1 if role == "winner" else -1
        net[player_id] = net.get(player_id, 0) + sign * amount
    return net


def session_balances(
    player_ids: Iterable[int], rounds: Iterable[Iterable[Participant]]
) -> dict[int, int]:
    """Compute every player's net cents across rounds, starting from zero."""
    balances = {player_id: 0 for player_id in player_ids}
    for participants in rounds:
        for player_id, delta in round_net(participants).items():
            balances[player_id] = balances.get(player_id, 0) + delta
    return balances
