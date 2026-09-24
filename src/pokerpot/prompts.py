"""Interactive prompt helpers used by the CLI commands."""

from __future__ import annotations

import sqlite3

import typer

from pokerpot import repo
from pokerpot.errors import NotFoundError
from pokerpot.render import console, player_table


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
