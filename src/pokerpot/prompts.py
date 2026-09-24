"""Interactive prompt helpers used by the CLI commands."""

from __future__ import annotations

import sqlite3

import typer

from pokerpot import accounting, repo
from pokerpot.errors import NotFoundError, StateError, ValidationError
from pokerpot.money import format_money, parse_money
from pokerpot.render import console, delta_table, player_table


def resolve_player_token(
    conn: sqlite3.Connection,
    token: str,
    roster: list[repo.Player] | None = None,
) -> repo.Player | None:
    """Resolve a token to a player.

    Tokens may be a 1-based roster position, a player name, or a numeric player
    ID. Unknown names are offered for creation. Returns ``None`` when the user
    declines to create an unknown player.
    """
    token = token.strip()
    if not token:
        return None
    if roster is not None and token.isdigit() and 1 <= int(token) <= len(roster):
        return roster[int(token) - 1]
    try:
        return repo.get_player(conn, token)
    except NotFoundError:
        pass
    name = repo.clean_player_name(token)
    if typer.confirm(f"Player {name!r} does not exist. Create it?", default=True):
        return repo.add_player(conn, name)
    return None


def select_players(conn: sqlite3.Connection) -> list[repo.Player]:
    """Prompt until at least one player is selected, creating new ones on demand."""
    players = repo.list_players(conn)
    if players:
        console.print(player_table(players))
    else:
        console.print("No players yet; you can create them now by typing names.")
    while True:
        raw = typer.prompt("Players (numbers or names, comma-separated)")
        tokens = [token.strip() for token in raw.split(",") if token.strip()]
        selected: list[repo.Player] = []
        for token in tokens:
            player = resolve_player_token(conn, token, roster=players)
            if player is not None and player not in selected:
                selected.append(player)
        if selected:
            return selected
        console.print("[yellow]Select at least one player.[/yellow]")


def prompt_money(label: str) -> int:
    """Prompt until the user enters a valid positive amount."""
    while True:
        raw = typer.prompt(label)
        try:
            return parse_money(raw)
        except ValidationError as exc:
            console.print(f"[yellow]{exc}[/yellow]")


def ask_round(
    conn: sqlite3.Connection, session: repo.Session, roster: list[repo.Player]
) -> tuple[dict[int, int], dict[int, int]] | None:
    """Interactively collect one round.

    Returns ``(loser_amounts, winner_amounts)`` keyed by player ID, or ``None``
    when the user cancels at the final confirmation.
    """
    if len(roster) < 2:
        raise StateError(
            "Recording a round needs at least two players in the session. "
            "Add one with: pokerpot session add-player NAME"
        )
    number = repo.next_round_number(conn, session.id)
    used: set[int] = set()
    console.print(f"\n[bold]Round {number}[/bold]\n")

    def pick(role_label: str) -> repo.Player:
        while True:
            available = [player for player in roster if player.id not in used]
            console.print(
                "  ".join(
                    f"[dim]{index})[/dim] {player.name}"
                    for index, player in enumerate(available, start=1)
                )
            )
            token = typer.prompt(role_label).strip()
            if token.isdigit() and 1 <= int(token) <= len(available):
                return available[int(token) - 1]
            try:
                player = repo.get_player(conn, token)
            except NotFoundError:
                try:
                    name = repo.clean_player_name(token)
                except ValidationError as exc:
                    console.print(f"[yellow]{exc}[/yellow]")
                    continue
                if not typer.confirm(
                    f"Player {name!r} does not exist. Create and add to session?", default=True
                ):
                    continue
                player = repo.add_player(conn, name)
                repo.add_session_player(conn, session.id, str(player.id))
                roster[:] = repo.session_players(conn, session.id)
                return player
            if player.id in used:
                console.print(f"[yellow]{player.name} is already in this round.[/yellow]")
                continue
            if player.id not in {member.id for member in roster}:
                if not typer.confirm(
                    f"Player {player.name!r} is not in this session. Add them?", default=True
                ):
                    continue
                repo.add_session_player(conn, session.id, str(player.id))
                roster[:] = repo.session_players(conn, session.id)
            return player

    losers: dict[int, int] = {}
    while True:
        player = pick("Loser")
        losers[player.id] = prompt_money(f"Amount for {player.name}")
        used.add(player.id)
        if not typer.confirm("Add another loser?", default=True):
            break
    pot = sum(losers.values())
    console.print(f"Pot: [bold]{format_money(pot)}[/bold]\n")

    winner_order: list[repo.Player] = []
    while True:
        player = pick("Winner")
        winner_order.append(player)
        used.add(player.id)
        if not typer.confirm("Add another winner?", default=False):
            break
    winner_ids = [player.id for player in winner_order]
    if len(winner_ids) > 1 and not typer.confirm("Split the pot equally?", default=True):
        while True:
            winners = {
                player.id: prompt_money(f"Amount for {player.name}") for player in winner_order
            }
            try:
                accounting.validate_round(losers, winners)
                break
            except ValidationError as exc:
                console.print(f"[yellow]{exc}[/yellow]")
    else:
        winners = accounting.equal_winner_amounts(pot, winner_ids)
        accounting.validate_round(losers, winners)

    names = {player.id: player.name for player in roster} | {
        player.id: player.name for player in winner_order
    }
    entries = [(names[player_id], -amount) for player_id, amount in losers.items()]
    entries += [(names[player_id], amount) for player_id, amount in winners.items()]
    console.print(delta_table(entries))
    if typer.confirm("Record this round?", default=True):
        return losers, winners
    return None
