from __future__ import annotations

import sqlite3

from pokerpot import accounting, repo
from pokerpot.errors import NotFoundError
from pokerpot.stats import SessionRecord, compute_player_stats, round_div


def _id(conn: sqlite3.Connection, name: str) -> int:
    try:
        return repo.get_player(conn, name).id
    except NotFoundError:
        return repo.add_player(conn, name).id


def _record_from_session(conn: sqlite3.Connection, session: repo.Session) -> SessionRecord:
    return SessionRecord(
        session=session,
        player_ids=[player.id for player in repo.session_players(conn, session.id)],
        rounds=repo.list_rounds(conn, session.id),
    )


def _play(
    conn: sqlite3.Connection,
    name: str,
    players: list[str],
    rounds: list[tuple[dict[str, int], list[str]]],
) -> SessionRecord:
    """Create and end a session with equal-split rounds.

    ``rounds`` is a list of ``(losers_by_name, winner_names)``.
    """
    ids = {player: _id(conn, player) for player in players}
    session = repo.start_session(conn, name, list(ids.values()))
    for losers, winners in rounds:
        loser_amounts = {ids[loser]: amount for loser, amount in losers.items()}
        pot = sum(loser_amounts.values())
        winner_amounts = accounting.equal_winner_amounts(pot, [ids[winner] for winner in winners])
        repo.add_round(conn, session.id, loser_amounts, winner_amounts)
    repo.end_session(conn, session.id)
    return _record_from_session(conn, session)


def test_round_div_half_away_from_zero() -> None:
    assert round_div(301, 2) == 151
    assert round_div(-301, 2) == -151
    assert round_div(1, 3) == 0
    assert round_div(2, 3) == 1
    assert round_div(-2, 3) == -1


def test_stats_totals(conn: sqlite3.Connection) -> None:
    alice = _id(conn, "Alice")
    records = [
        _play(conn, "Night 1", ["Alice", "Bob"], [({"Alice": 2000}, ["Bob"])]),
        _play(conn, "Night 2", ["Alice", "Bob"], [({"Bob": 5000}, ["Alice"])]),
    ]
    stats = compute_player_stats(alice, records)
    assert stats.sessions_played == 2
    assert stats.total_net_cents == 3000
    assert stats.total_won_cents == 5000
    assert stats.total_lost_cents == 2000
    assert stats.profitable_sessions == 1
    assert stats.losing_sessions == 1
    assert stats.break_even_sessions == 0
    assert stats.session_win_rate == 0.5
    assert stats.rounds_played == 2
    assert stats.rounds_won == 1
    assert stats.rounds_lost == 1
    assert stats.round_win_rate == 0.5
    assert stats.average_session_cents == 1500
    assert stats.median_session_cents == 1500
    assert stats.best_session_cents == 5000
    assert stats.worst_session_cents == -2000
    assert stats.best_round_win_cents == 5000
    assert stats.worst_round_loss_cents == 2000
    assert stats.average_winning_round_cents == 5000
    assert stats.average_losing_round_cents == 2000
    assert stats.longest_winning_streak == 1
    assert stats.longest_losing_streak == 1


def test_stats_median_rounds_half_away(conn: sqlite3.Connection) -> None:
    alice = _id(conn, "Alice")
    records = [
        _play(conn, "Night 1", ["Alice", "Bob"], [({"Bob": 100}, ["Alice"])]),
        _play(conn, "Night 2", ["Alice", "Bob"], [({"Bob": 201}, ["Alice"])]),
    ]
    stats = compute_player_stats(alice, records)
    assert stats.total_net_cents == 301
    assert stats.average_session_cents == 151
    assert stats.median_session_cents == 151


def test_stats_streaks_break_even_resets(conn: sqlite3.Connection) -> None:
    alice = _id(conn, "Alice")
    records = [
        _play(conn, "Win 1", ["Alice", "Bob"], [({"Bob": 100}, ["Alice"])]),
        _play(
            conn,
            "Break even",
            ["Alice", "Bob"],
            [({"Alice": 50}, ["Bob"]), ({"Bob": 50}, ["Alice"])],
        ),
        _play(conn, "Win 2", ["Alice", "Bob"], [({"Bob": 100}, ["Alice"])]),
        _play(conn, "Win 3", ["Alice", "Bob"], [({"Bob": 100}, ["Alice"])]),
        _play(conn, "Loss 1", ["Alice", "Bob"], [({"Alice": 100}, ["Bob"])]),
        _play(conn, "Loss 2", ["Alice", "Bob"], [({"Alice": 100}, ["Bob"])]),
        _play(conn, "Loss 3", ["Alice", "Bob"], [({"Alice": 100}, ["Bob"])]),
    ]
    stats = compute_player_stats(alice, records)
    assert stats.sessions_played == 7
    assert stats.break_even_sessions == 1
    assert stats.longest_winning_streak == 2
    assert stats.longest_losing_streak == 3


def test_stats_break_even_counts_in_win_rate(conn: sqlite3.Connection) -> None:
    alice = _id(conn, "Alice")
    records = [
        _play(conn, "Win", ["Alice", "Bob"], [({"Bob": 100}, ["Alice"])]),
        _play(
            conn,
            "Break even",
            ["Alice", "Bob"],
            [({"Alice": 50}, ["Bob"]), ({"Bob": 50}, ["Alice"])],
        ),
    ]
    stats = compute_player_stats(alice, records)
    assert stats.session_win_rate == 0.5


def test_stats_without_sessions(conn: sqlite3.Connection) -> None:
    alice = _id(conn, "Alice")
    stats = compute_player_stats(alice, [])
    assert stats.sessions_played == 0
    assert stats.total_net_cents == 0
    assert stats.session_win_rate == 0.0
    assert stats.round_win_rate == 0.0
    assert stats.best_session_cents is None
    assert stats.worst_session_cents is None
    assert stats.best_round_win_cents is None
    assert stats.average_winning_round_cents is None


def test_stats_round_averages(conn: sqlite3.Connection) -> None:
    alice = _id(conn, "Alice")
    records = [
        _play(
            conn,
            "Night",
            ["Alice", "Bob", "Carol"],
            [
                ({"Bob": 3000}, ["Alice"]),
                ({"Alice": 500}, ["Carol"]),
                ({"Alice": 700}, ["Bob"]),
            ],
        )
    ]
    stats = compute_player_stats(alice, records)
    assert stats.rounds_played == 3
    assert stats.rounds_won == 1
    assert stats.rounds_lost == 2
    assert stats.total_round_won_cents == 3000
    assert stats.total_round_lost_cents == 1200
    assert stats.best_round_win_cents == 3000
    assert stats.worst_round_loss_cents == 700
    assert stats.average_winning_round_cents == 3000
    assert stats.average_losing_round_cents == 600


def test_stats_ignore_players_not_in_session(conn: sqlite3.Connection) -> None:
    records = [
        _play(conn, "Night", ["Alice", "Bob"], [({"Bob": 100}, ["Alice"])]),
    ]
    carol = _id(conn, "Carol")
    stats = compute_player_stats(carol, records)
    assert stats.sessions_played == 0
