"""Rich console helpers shared by the CLI commands."""

from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.table import Table

from poker.money import format_money
from poker.repo import Participant, Player, Round, Session
from poker.stats import PlayerStats

console = Console()
err_console = Console(stderr=True)


def local_time(iso_timestamp: str) -> str:
    """Render a stored UTC timestamp in the local timezone."""
    return datetime.fromisoformat(iso_timestamp).astimezone().strftime("%Y-%m-%d %H:%M")


def session_table(sessions: list[Session]) -> Table:
    table = Table(header_style="bold")
    table.add_column("ID", justify="right", style="dim")
    table.add_column("Name")
    table.add_column("Status")
    table.add_column("Players", justify="right")
    table.add_column("Rounds", justify="right")
    table.add_column("Started")
    table.add_column("Ended")
    for session in sessions:
        status = "[green]active[/green]" if session.status == "active" else "[dim]completed[/dim]"
        table.add_row(
            str(session.id),
            session.name,
            status,
            str(session.player_count),
            str(session.round_count),
            local_time(session.started_at),
            local_time(session.ended_at) if session.ended_at else "-",
        )
    return table


def _rate(rate: float, played: int) -> str:
    return "—" if not played else f"{rate * 100:.1f}%"


def _optional_money(cents: int | None, *, plus: bool = True) -> str:
    return "—" if cents is None else format_money(cents, plus=plus)


def _optional_loss(cents: int | None) -> str:
    return "—" if cents is None else format_money(-cents)


def stats_table(players: list[Player], stats_by_id: dict[int, PlayerStats]) -> Table:
    table = Table(header_style="bold")
    table.add_column("Player")
    table.add_column("Sessions", justify="right")
    table.add_column("Net", justify="right")
    table.add_column("Won", justify="right")
    table.add_column("Lost", justify="right")
    table.add_column("Win %", justify="right")
    table.add_column("Rounds", justify="right")
    table.add_column("Round win %", justify="right")
    entries = sorted(
        players, key=lambda player: (-stats_by_id[player.id].total_net_cents, player.name.lower())
    )
    for player in entries:
        player_stats = stats_by_id[player.id]
        table.add_row(
            player.name,
            str(player_stats.sessions_played),
            format_money(player_stats.total_net_cents, plus=True),
            format_money(player_stats.total_won_cents),
            format_money(player_stats.total_lost_cents),
            _rate(player_stats.session_win_rate, player_stats.sessions_played),
            str(player_stats.rounds_played),
            _rate(player_stats.round_win_rate, player_stats.rounds_played),
        )
    return table


def stats_detail_table(player_stats: PlayerStats, name: str) -> Table:
    table = Table(title=f"Statistics for {name}", header_style="bold", show_header=False)
    table.add_column("Statistic")
    table.add_column("Value", justify="right")
    rows = [
        ("Sessions played", str(player_stats.sessions_played)),
        ("Total net", format_money(player_stats.total_net_cents, plus=True)),
        ("Total won (session totals)", format_money(player_stats.total_won_cents)),
        ("Total lost (session totals)", format_money(player_stats.total_lost_cents)),
        ("Profitable sessions", str(player_stats.profitable_sessions)),
        ("Losing sessions", str(player_stats.losing_sessions)),
        ("Break-even sessions", str(player_stats.break_even_sessions)),
        ("Session win rate", _rate(player_stats.session_win_rate, player_stats.sessions_played)),
        ("Average session", format_money(player_stats.average_session_cents, plus=True)),
        ("Median session", format_money(player_stats.median_session_cents, plus=True)),
        ("Best session", _optional_money(player_stats.best_session_cents)),
        ("Worst session", _optional_money(player_stats.worst_session_cents)),
        ("Longest winning streak", str(player_stats.longest_winning_streak)),
        ("Longest losing streak", str(player_stats.longest_losing_streak)),
        ("Rounds played", str(player_stats.rounds_played)),
        ("Rounds won", str(player_stats.rounds_won)),
        ("Rounds lost", str(player_stats.rounds_lost)),
        ("Round win rate", _rate(player_stats.round_win_rate, player_stats.rounds_played)),
        ("Total from winning rounds", format_money(player_stats.total_round_won_cents)),
        ("Total lost in losing rounds", format_money(player_stats.total_round_lost_cents)),
        ("Best single-round win", _optional_money(player_stats.best_round_win_cents)),
        ("Worst single-round loss", _optional_loss(player_stats.worst_round_loss_cents)),
        ("Average winning round", _optional_money(player_stats.average_winning_round_cents)),
        ("Average losing round", _optional_loss(player_stats.average_losing_round_cents)),
    ]
    for label, value in rows:
        table.add_row(label, value)
    return table


def delta_table(entries: list[tuple[str, int]]) -> Table:
    table = Table(header_style="bold", show_header=False, box=None, pad_edge=False)
    table.add_column("Player")
    table.add_column("Amount", justify="right")
    for name, delta in entries:
        style = "green" if delta > 0 else "red"
        table.add_row(name, f"[{style}]{format_money(delta, plus=True)}[/{style}]")
    return table


def balance_table(players: list[Player], balances: dict[int, int]) -> Table:
    table = Table(header_style="bold")
    table.add_column("Player")
    table.add_column("Balance", justify="right")
    entries = sorted(
        ((player.name, balances.get(player.id, 0)) for player in players),
        key=lambda item: (-item[1], item[0].lower()),
    )
    for name, balance in entries:
        style = "green" if balance > 0 else ("red" if balance < 0 else "dim")
        table.add_row(name, f"[{style}]{format_money(balance, plus=True)}[/{style}]")
    table.add_section()
    total = sum(balances.values())
    table.add_row("[bold]Total[/bold]", f"[bold]{format_money(total, plus=True)}[/bold]")
    return table


def settlement_table(transfers: list[tuple[int, int, int]], names: dict[int, str]) -> Table:
    table = Table(header_style="bold")
    table.add_column("From")
    table.add_column("To")
    table.add_column("Amount", justify="right")
    for from_id, to_id, amount in transfers:
        table.add_row(names[from_id], names[to_id], format_money(amount))
    return table


def _participants_text(participants: tuple[Participant, ...]) -> str:
    return ", ".join(
        f"{participant.player_name} {format_money(participant.amount_cents)}"
        for participant in participants
    )


def round_table(rounds: list[Round]) -> Table:
    table = Table(header_style="bold")
    table.add_column("#", justify="right")
    table.add_column("Pot", justify="right")
    table.add_column("Losers")
    table.add_column("Winners")
    for round_ in rounds:
        table.add_row(
            str(round_.number),
            format_money(round_.pot_cents),
            _participants_text(round_.losers),
            _participants_text(round_.winners),
        )
    return table


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
