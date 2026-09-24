"""Command-line interface for PokerPot."""

from __future__ import annotations

import functools
import sqlite3
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TypeVar, cast

import typer

from pokerpot import __version__, db, repo
from pokerpot.errors import PokerPotError
from pokerpot.render import console, err_console, local_time, player_table

app = typer.Typer(
    name="pokerpot",
    help="Track poker-night money between friends: rounds, balances, settlement.",
    no_args_is_help=True,
    add_completion=False,
)
player_app = typer.Typer(help="Manage players.", no_args_is_help=True)
app.add_typer(player_app, name="player")

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class AppState:
    db_path: Path | None = None


def handle_errors(func: F) -> F:
    """Convert domain and database errors into clean CLI exits."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except PokerPotError as exc:
            err_console.print(f"[bold red]Error:[/bold red] {exc}")
            raise typer.Exit(1) from exc
        except sqlite3.Error as exc:  # pragma: no cover - safety net
            err_console.print(f"[bold red]Database error:[/bold red] {exc}")
            raise typer.Exit(1) from exc

    return cast(F, wrapper)


@contextmanager
def _db(ctx: typer.Context) -> Iterator[sqlite3.Connection]:
    state = ctx.obj if isinstance(ctx.obj, AppState) else AppState()
    conn = db.connect(db.resolve_db_path(state.db_path))
    try:
        yield conn
    finally:
        conn.close()


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"pokerpot {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_show_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
    db_path: Path | None = typer.Option(
        None,
        "--db",
        metavar="PATH",
        help="Use a specific database file instead of the default location.",
        show_default=False,
    ),
) -> None:
    """PokerPot: a local-only CLI ledger for poker sessions."""
    ctx.obj = AppState(db_path=db_path)


@player_app.command("add")
@handle_errors
def player_add(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Name of the new player."),
) -> None:
    """Create a new player."""
    with _db(ctx) as conn:
        player = repo.add_player(conn, name)
    console.print(f"Added player [bold]{player.name}[/bold] (id {player.id}).")


@player_app.command("list")
@handle_errors
def player_list(ctx: typer.Context) -> None:
    """List all players."""
    with _db(ctx) as conn:
        players = repo.list_players(conn)
    if not players:
        console.print("No players yet. Add one with: pokerpot player add NAME")
        return
    console.print(player_table(players))


@player_app.command("show")
@handle_errors
def player_show(
    ctx: typer.Context,
    player: str = typer.Argument(..., help="Player name or ID."),
) -> None:
    """Show one player and a quick summary."""
    with _db(ctx) as conn:
        found = repo.get_player(conn, player)
    console.print(f"ID:       {found.id}")
    console.print(f"Name:     [bold]{found.name}[/bold]")
    console.print(f"Created:  {local_time(found.created_at)}")
    console.print(f"Sessions: {found.session_count}")
    console.print(f"Rounds:   {found.round_count}")


@player_app.command("rename")
@handle_errors
def player_rename(
    ctx: typer.Context,
    player: str = typer.Argument(..., help="Current player name or ID."),
    new_name: str = typer.Argument(..., help="New name for the player."),
) -> None:
    """Rename a player; history stays attached."""
    with _db(ctx) as conn:
        renamed = repo.rename_player(conn, player, new_name)
    console.print(f"Renamed player to [bold]{renamed.name}[/bold].")


@player_app.command("delete")
@handle_errors
def player_delete(
    ctx: typer.Context,
    player: str = typer.Argument(..., help="Player name or ID."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Delete a player that has no recorded rounds."""
    with _db(ctx) as conn:
        found = repo.get_player(conn, player)
        if not yes:
            typer.confirm(
                f"Delete player {found.name!r}? This cannot be undone.",
                abort=True,
            )
        repo.delete_player(conn, str(found.id))
    console.print(f"Deleted player [bold]{found.name}[/bold].")
