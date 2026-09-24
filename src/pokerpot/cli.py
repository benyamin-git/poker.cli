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

from pokerpot import __version__, accounting, db, prompts, repo
from pokerpot.errors import NotFoundError, PokerPotError, StateError, ValidationError
from pokerpot.money import format_money, parse_money
from pokerpot.render import (
    console,
    delta_table,
    err_console,
    local_time,
    player_table,
    round_table,
    session_table,
)

app = typer.Typer(
    name="pokerpot",
    help="Track poker-night money between friends: rounds, balances, settlement.",
    no_args_is_help=True,
    add_completion=False,
)
player_app = typer.Typer(help="Manage players.", no_args_is_help=True)
session_app = typer.Typer(help="Manage poker sessions.", no_args_is_help=True)
round_app = typer.Typer(help="Record and inspect rounds.", no_args_is_help=False)
app.add_typer(player_app, name="player")
app.add_typer(session_app, name="session")
app.add_typer(round_app, name="round")

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


def _parse_session_id(ref: str | None) -> int | None:
    if ref is None:
        return None
    if not ref.strip().isdigit():
        raise NotFoundError(f"Invalid session ID {ref!r}; expected a number.")
    return int(ref)


def _require_session(conn: sqlite3.Connection, ref: str | None) -> repo.Session:
    session_id = _parse_session_id(ref)
    if session_id is None:
        return repo.require_active_session(conn)
    return repo.get_session(conn, session_id)


def _resolve_players_arg(conn: sqlite3.Connection, raw: str) -> list[repo.Player]:
    tokens = [token.strip() for token in raw.split(",") if token.strip()]
    if not tokens:
        raise ValidationError("--players needs at least one player name or ID.")
    players: list[repo.Player] = []
    for token in tokens:
        player = repo.get_player(conn, token)
        if player not in players:
            players.append(player)
    return players


@session_app.command("start")
@handle_errors
def session_start(
    ctx: typer.Context,
    name: str | None = typer.Option(None, "--name", "-n", help="Optional session name."),
    players_arg: str | None = typer.Option(
        None,
        "--players",
        help="Comma-separated player names or IDs (skips the interactive picker).",
    ),
) -> None:
    """Start a new poker session."""
    with _db(ctx) as conn:
        if players_arg is not None:
            players = _resolve_players_arg(conn, players_arg)
        else:
            players = prompts.select_players(conn)
        session = repo.start_session(conn, name, [player.id for player in players])
    console.print(f"Started session [bold]{session.name}[/bold] (id {session.id}).")
    console.print("Record rounds with: pokerpot round")


@session_app.command("list")
@handle_errors
def session_list(ctx: typer.Context) -> None:
    """List all sessions."""
    with _db(ctx) as conn:
        sessions = repo.list_sessions(conn)
    if not sessions:
        console.print("No sessions yet. Start one with: pokerpot session start")
        return
    console.print(session_table(sessions))


@session_app.command("show")
@handle_errors
def session_show(
    ctx: typer.Context,
    session: str | None = typer.Argument(None, help="Session ID (defaults to the active session)."),
    rounds: bool = typer.Option(False, "--rounds", help="Also list every round."),
) -> None:
    """Show a session and its players."""
    with _db(ctx) as conn:
        found = _require_session(conn, session)
        players = repo.session_players(conn, found.id)
        recorded_rounds = repo.list_rounds(conn, found.id) if rounds else []
    console.print(f"Session:  [bold]{found.name}[/bold]")
    console.print(f"ID:       {found.id}")
    console.print(f"Status:   {found.status}")
    console.print(f"Started:  {local_time(found.started_at)}")
    console.print(f"Ended:    {local_time(found.ended_at) if found.ended_at else '-'}")
    console.print(f"Rounds:   {found.round_count}")
    console.print()
    if players:
        console.print(player_table(players))
    else:
        console.print("No players in this session.")
    if rounds:
        console.print()
        if recorded_rounds:
            console.print(round_table(recorded_rounds))
        else:
            console.print("No rounds recorded yet.")


@session_app.command("add-player")
@handle_errors
def session_add_player(
    ctx: typer.Context,
    player: str = typer.Argument(..., help="Player name or ID; unknown names are created."),
) -> None:
    """Add a player to the active session."""
    with _db(ctx) as conn:
        session = repo.require_active_session(conn)
        found, created = repo.add_session_player(conn, session.id, player)
    if created:
        console.print(f"Created player [bold]{found.name}[/bold] and added them to the session.")
    else:
        console.print(f"Added [bold]{found.name}[/bold] to the session.")


@session_app.command("remove-player")
@handle_errors
def session_remove_player(
    ctx: typer.Context,
    player: str = typer.Argument(..., help="Player name or ID."),
) -> None:
    """Remove a player from the active session (only if they have no rounds)."""
    with _db(ctx) as conn:
        session = repo.require_active_session(conn)
        found = repo.remove_session_player(conn, session.id, player)
    console.print(f"Removed [bold]{found.name}[/bold] from the session.")


@session_app.command("end")
@handle_errors
def session_end(
    ctx: typer.Context,
    session: str | None = typer.Argument(None, help="Session ID (defaults to the active session)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """End a poker session."""
    with _db(ctx) as conn:
        found = _require_session(conn, session)
        if not yes:
            typer.confirm(f"End session {found.name!r}?", abort=True)
        ended = repo.end_session(conn, found.id)
    console.print(f"Session [bold]{ended.name}[/bold] (id {ended.id}) ended.")
    console.print(f"View it with: pokerpot session show {ended.id}")


@session_app.command("reopen")
@handle_errors
def session_reopen(
    ctx: typer.Context,
    session: str = typer.Argument(..., help="Session ID."),
) -> None:
    """Reopen a completed session so it can be corrected."""
    with _db(ctx) as conn:
        session_id = _parse_session_id(session)
        if session_id is None:  # pragma: no cover - the argument is required
            raise ValidationError("A session ID is required.")
        reopened = repo.reopen_session(conn, session_id)
    console.print(f"Session [bold]{reopened.name}[/bold] (id {reopened.id}) reopened.")


def _participant_names(conn: sqlite3.Connection, player_ids: list[int]) -> dict[int, str]:
    return {player_id: repo.get_player(conn, str(player_id)).name for player_id in player_ids}


def _parse_loser_args(conn: sqlite3.Connection, tokens: list[str]) -> dict[int, int]:
    if not tokens:
        raise ValidationError("A round needs at least one --loser NAME=AMOUNT.")
    losers: dict[int, int] = {}
    for token in tokens:
        name, separator, amount_text = token.partition("=")
        if not separator or not name.strip() or not amount_text.strip():
            raise ValidationError(f"--loser expects NAME=AMOUNT, got {token!r}.")
        player = repo.get_player(conn, name.strip())
        if player.id in losers:
            raise ValidationError(f"{player.name} is listed twice as a loser.")
        losers[player.id] = parse_money(amount_text)
    return losers


def _parse_winner_args(
    conn: sqlite3.Connection, tokens: list[str], pot_cents: int
) -> dict[int, int]:
    if not tokens:
        raise ValidationError("A round needs at least one --winner NAME or NAME=AMOUNT.")
    order: list[int] = []
    amounts: dict[int, int] = {}
    with_amount = 0
    for token in tokens:
        name, separator, amount_text = token.partition("=")
        if not name.strip():
            raise ValidationError(f"--winner expects NAME or NAME=AMOUNT, got {token!r}.")
        player = repo.get_player(conn, name.strip())
        if player.id in order:
            raise ValidationError(f"{player.name} is listed twice as a winner.")
        order.append(player.id)
        if separator:
            if not amount_text.strip():
                raise ValidationError(f"--winner expects NAME or NAME=AMOUNT, got {token!r}.")
            amounts[player.id] = parse_money(amount_text)
            with_amount += 1
    if with_amount == 0:
        return accounting.equal_winner_amounts(pot_cents, order)
    if with_amount != len(order):
        raise ValidationError(
            "Give an amount for either all winners or none, so the pot split is unambiguous."
        )
    return amounts


def _preview_and_confirm(
    conn: sqlite3.Connection, losers: dict[int, int], winners: dict[int, int]
) -> bool:
    accounting.validate_round(losers, winners)
    names = _participant_names(conn, [*losers, *winners])
    entries = [(names[player_id], -amount) for player_id, amount in losers.items()]
    entries += [(names[player_id], amount) for player_id, amount in winners.items()]
    console.print(f"Pot: [bold]{format_money(sum(losers.values()))}[/bold]")
    console.print(delta_table(entries))
    return typer.confirm("Record this round?", default=True)


@round_app.callback(invoke_without_command=True)
@handle_errors
def round_group(ctx: typer.Context) -> None:
    """Record a round for the active session (interactive)."""
    if ctx.invoked_subcommand is not None:
        return
    with _db(ctx) as conn:
        session = repo.require_active_session(conn)
        roster = repo.session_players(conn, session.id)
        result = prompts.ask_round(conn, session, roster)
        if result is None:
            console.print("Round cancelled.")
            return
        losers, winners = result
        recorded = repo.add_round(conn, session.id, losers, winners)
    console.print(
        f"Recorded round [bold]{recorded.number}[/bold] (pot {format_money(recorded.pot_cents)})."
    )


@round_app.command("add")
@handle_errors
def round_add(
    ctx: typer.Context,
    loser: list[str] = typer.Option([], "--loser", help="Repeatable: NAME=AMOUNT."),
    winner: list[str] = typer.Option(
        [], "--winner", help="Repeatable: NAME or NAME=AMOUNT; omit amounts to split equally."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Record a round non-interactively."""
    with _db(ctx) as conn:
        session = repo.require_active_session(conn)
        losers = _parse_loser_args(conn, loser)
        winners = _parse_winner_args(conn, winner, sum(losers.values()))
        if not yes and not _preview_and_confirm(conn, losers, winners):
            console.print("Round cancelled.")
            return
        recorded = repo.add_round(conn, session.id, losers, winners)
    console.print(
        f"Recorded round [bold]{recorded.number}[/bold] (pot {format_money(recorded.pot_cents)})."
    )


@round_app.command("list")
@handle_errors
def round_list(
    ctx: typer.Context,
    session: str | None = typer.Argument(None, help="Session ID (defaults to the active session)."),
) -> None:
    """List the rounds of a session."""
    with _db(ctx) as conn:
        found = _require_session(conn, session)
        rounds = repo.list_rounds(conn, found.id)
    if not rounds:
        console.print("No rounds recorded yet.")
        return
    console.print(round_table(rounds))


@round_app.command("undo")
@handle_errors
def round_undo(
    ctx: typer.Context,
    session: str | None = typer.Argument(None, help="Session ID (defaults to the active session)."),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip the confirmation prompt."),
) -> None:
    """Remove the most recently recorded round."""
    with _db(ctx) as conn:
        found = _require_session(conn, session)
        last = repo.last_round(conn, found.id)
        if last is None:
            raise StateError("There are no rounds to undo in this session.")
        if not yes:
            console.print(round_table([last]))
            typer.confirm(f"Remove round {last.number}?", abort=True)
        removed = repo.undo_last_round(conn, found.id)
    console.print(f"Removed round {removed.number}.")
