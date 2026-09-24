from __future__ import annotations

import sqlite3

import pytest

from poker import repo
from poker.errors import StateError, ValidationError


@pytest.fixture
def session(conn: sqlite3.Connection) -> repo.Session:
    alice = repo.add_player(conn, "Alice")
    bob = repo.add_player(conn, "Bob")
    carol = repo.add_player(conn, "Carol")
    dave = repo.add_player(conn, "Dave")
    return repo.start_session(conn, "Test", [alice.id, bob.id, carol.id, dave.id])


def _ids(conn: sqlite3.Connection) -> dict[str, int]:
    return {player.name: player.id for player in repo.list_players(conn)}


def test_add_basic_round(conn: sqlite3.Connection, session: repo.Session) -> None:
    ids = _ids(conn)
    round_ = repo.add_round(conn, session.id, {ids["Alice"]: 2000}, {ids["Bob"]: 2000})
    assert round_.number == 1
    assert round_.pot_cents == 2000
    assert [(p.player_name, p.role, p.amount_cents) for p in round_.participants] == [
        ("Alice", "loser", 2000),
        ("Bob", "winner", 2000),
    ]
    assert repo.get_session(conn, session.id).round_count == 1


def test_add_multiple_losers_and_winners(conn: sqlite3.Connection, session: repo.Session) -> None:
    ids = _ids(conn)
    round_ = repo.add_round(
        conn,
        session.id,
        {ids["Alice"]: 2000, ids["Bob"]: 3000},
        {ids["Carol"]: 2500, ids["Dave"]: 2500},
    )
    assert round_.pot_cents == 5000


def test_round_numbers_increment_and_reuse_after_undo(
    conn: sqlite3.Connection, session: repo.Session
) -> None:
    ids = _ids(conn)
    first = repo.add_round(conn, session.id, {ids["Alice"]: 100}, {ids["Bob"]: 100})
    second = repo.add_round(conn, session.id, {ids["Alice"]: 100}, {ids["Bob"]: 100})
    assert (first.number, second.number) == (1, 2)
    repo.undo_last_round(conn, session.id)
    third = repo.add_round(conn, session.id, {ids["Alice"]: 100}, {ids["Bob"]: 100})
    assert third.number == 2


def test_add_round_rejects_imbalance(conn: sqlite3.Connection, session: repo.Session) -> None:
    ids = _ids(conn)
    with pytest.raises(ValidationError, match="does not balance"):
        repo.add_round(conn, session.id, {ids["Alice"]: 2000}, {ids["Bob"]: 1000})
    assert repo.get_session(conn, session.id).round_count == 0


def test_add_round_rejects_player_not_in_session(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    bob = repo.add_player(conn, "Bob")
    outsider = repo.add_player(conn, "Mallory")
    session = repo.start_session(conn, "Test", [alice.id, bob.id])
    with pytest.raises(ValidationError, match="not in session"):
        repo.add_round(conn, session.id, {alice.id: 100}, {outsider.id: 100})


def test_add_round_rejects_ended_session(conn: sqlite3.Connection, session: repo.Session) -> None:
    ids = _ids(conn)
    repo.end_session(conn, session.id)
    with pytest.raises(StateError, match="has ended"):
        repo.add_round(conn, session.id, {ids["Alice"]: 100}, {ids["Bob"]: 100})


def test_list_rounds_in_order(conn: sqlite3.Connection, session: repo.Session) -> None:
    ids = _ids(conn)
    repo.add_round(conn, session.id, {ids["Alice"]: 100}, {ids["Bob"]: 100})
    repo.add_round(conn, session.id, {ids["Bob"]: 200}, {ids["Carol"]: 200})
    rounds = repo.list_rounds(conn, session.id)
    assert [round_.number for round_ in rounds] == [1, 2]
    assert rounds[0].losers[0].player_name == "Alice"
    assert rounds[0].winners[0].player_name == "Bob"


def test_undo_last_round(conn: sqlite3.Connection, session: repo.Session) -> None:
    ids = _ids(conn)
    repo.add_round(conn, session.id, {ids["Alice"]: 100}, {ids["Bob"]: 100})
    repo.add_round(conn, session.id, {ids["Bob"]: 200}, {ids["Carol"]: 200})
    removed = repo.undo_last_round(conn, session.id)
    assert removed.number == 2
    rounds = repo.list_rounds(conn, session.id)
    assert [round_.number for round_ in rounds] == [1]
    assert repo.get_session(conn, session.id).round_count == 1


def test_undo_without_rounds(conn: sqlite3.Connection, session: repo.Session) -> None:
    with pytest.raises(StateError, match="no rounds to undo"):
        repo.undo_last_round(conn, session.id)


def test_undo_rejects_ended_session(conn: sqlite3.Connection, session: repo.Session) -> None:
    ids = _ids(conn)
    repo.add_round(conn, session.id, {ids["Alice"]: 100}, {ids["Bob"]: 100})
    repo.end_session(conn, session.id)
    with pytest.raises(StateError, match="has ended"):
        repo.undo_last_round(conn, session.id)


def test_get_round_unknown(conn: sqlite3.Connection) -> None:
    from poker.errors import NotFoundError

    with pytest.raises(NotFoundError):
        repo.get_round(conn, 99)
