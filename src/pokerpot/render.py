"""Rich console helpers shared by the CLI commands."""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.table import Table

from pokerpot.repo import Player

console = Console()
err_console = Console(stderr=True)


def local_time(iso_timestamp: str) -> str:
    """Render a stored UTC timestamp in the local timezone."""
    return datetime.fromisoformat(iso_timestamp).astimezone().strftime("%Y-%m-%d %H:%M")


def player_table(players: list[Player]) -> Table:
    table = Table(header_style="bold")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Name")
    table.add_column("Sessions", justify="right")
    table.add_column("Rounds", justify="right")
    table.add_column("Created")
    for player in players:
        table.add_row(
            str(player.id),
            player.name,
            str(player.session_count),
            str(player.round_count),
            local_time(player.created_at),
        )
    return table
