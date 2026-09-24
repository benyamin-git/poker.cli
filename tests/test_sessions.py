from __future__ import annotations

import sqlite3

import pytest

from poker import repo
from poker.errors import ConflictError, NotFoundError, StateError, ValidationError


def _players(conn: sqlite3.Connection, *names: str) -> list[repo.Player]:
    return [repo.add_player(conn, name) for name in names]


def test_start_session_with_players(conn: sqlite3.Connection) -> None:
    alice, bob = _players(conn, "Alice", "Bob")
    session = repo.start_session(conn, "Friday Poker", [alice.id, bob.id])
    assert session.name == "Friday Poker"
    assert session.status == "active"
    assert session.ended_at is None
    assert session.player_count == 2
    assert [player.name for player in repo.session_players(conn, session.id)] == ["Alice", "Bob"]


def test_start_session_default_name(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, None, [alice.id])
    assert session.name.startswith("Session ")


def test_start_session_trims_name(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, "  Big   Night  ", [alice.id])
    assert session.name == "Big Night"


def test_start_session_empty_name_rejected(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    with pytest.raises(ValidationError):
        repo.start_session(conn, "   ", [alice.id])


def test_start_session_requires_players(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValidationError):
        repo.start_session(conn, "No Players", [])


def test_start_session_deduplicates_players(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, "Solo", [alice.id, alice.id])
    assert session.player_count == 1


def test_start_session_unknown_player(conn: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        repo.start_session(conn, "Ghosts", [999])


def test_only_one_active_session(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    repo.start_session(conn, "First", [alice.id])
    with pytest.raises(StateError, match="already active"):
        repo.start_session(conn, "Second", [alice.id])


def test_list_sessions_orders_active_first(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    first = repo.start_session(conn, "First", [alice.id])
    repo.end_session(conn, first.id)
    second = repo.start_session(conn, "Second", [alice.id])
    sessions = repo.list_sessions(conn)
    assert [session.id for session in sessions] == [second.id, first.id]
    assert [session.name for session in repo.list_sessions(conn, "completed")] == ["First"]


def test_add_session_player_existing(conn: sqlite3.Connection) -> None:
    alice, bob = _players(conn, "Alice", "Bob")
    session = repo.start_session(conn, None, [alice.id])
    player, created = repo.add_session_player(conn, session.id, "Bob")
    assert player.id == bob.id
    assert created is False
    assert repo.get_session(conn, session.id).player_count == 2


def test_add_session_player_creates_unknown(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, None, [alice.id])
    player, created = repo.add_session_player(conn, session.id, "Carol")
    assert created is True
    assert player.name == "Carol"
    assert repo.get_session(conn, session.id).player_count == 2


def test_add_session_player_duplicate(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, None, [alice.id])
    with pytest.raises(ConflictError, match="already in this session"):
        repo.add_session_player(conn, session.id, "Alice")


def test_add_session_player_to_ended_session(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, None, [alice.id])
    repo.end_session(conn, session.id)
    with pytest.raises(StateError, match="has ended"):
        repo.add_session_player(conn, session.id, "Bob")


def test_remove_session_player(conn: sqlite3.Connection) -> None:
    alice, bob = _players(conn, "Alice", "Bob")
    session = repo.start_session(conn, None, [alice.id, bob.id])
    removed = repo.remove_session_player(conn, session.id, "Bob")
    assert removed.name == "Bob"
    assert repo.get_session(conn, session.id).player_count == 1
    assert repo.get_player(conn, "Bob").session_count == 0


def test_remove_session_player_not_in_session(conn: sqlite3.Connection) -> None:
    alice, bob = _players(conn, "Alice", "Bob")
    session = repo.start_session(conn, None, [alice.id])
    with pytest.raises(NotFoundError, match="not in session"):
        repo.remove_session_player(conn, session.id, "Bob")


def test_remove_session_player_with_rounds_refused(conn: sqlite3.Connection) -> None:
    alice, bob = _players(conn, "Alice", "Bob")
    session = repo.start_session(conn, None, [alice.id, bob.id])
    now = repo.now_utc()
    with conn:
        round_id = conn.execute(
            "INSERT INTO rounds (session_id, number, created_at) VALUES (?, 1, ?)",
            (session.id, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO round_participants (round_id, player_id, role, amount_cents) "
            "VALUES (?, ?, 'winner', 100)",
            (round_id, bob.id),
        )
    with pytest.raises(ConflictError, match="cannot be removed"):
        repo.remove_session_player(conn, session.id, "Bob")


def test_end_session(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, None, [alice.id])
    ended = repo.end_session(conn, session.id)
    assert ended.status == "completed"
    assert ended.ended_at is not None
    assert repo.get_active_session(conn) is None


def test_end_session_twice(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, None, [alice.id])
    repo.end_session(conn, session.id)
    with pytest.raises(StateError, match="already ended"):
        repo.end_session(conn, session.id)


def test_reopen_session(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, None, [alice.id])
    repo.end_session(conn, session.id)
    reopened = repo.reopen_session(conn, session.id)
    assert reopened.status == "active"
    assert reopened.ended_at is None


def test_reopen_active_session(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    session = repo.start_session(conn, None, [alice.id])
    with pytest.raises(StateError, match="already active"):
        repo.reopen_session(conn, session.id)


def test_reopen_while_another_session_active(conn: sqlite3.Connection) -> None:
    alice = repo.add_player(conn, "Alice")
    first = repo.start_session(conn, "First", [alice.id])
    repo.end_session(conn, first.id)
    repo.start_session(conn, "Second", [alice.id])
    with pytest.raises(StateError, match="still active"):
        repo.reopen_session(conn, first.id)


def test_get_unknown_session(conn: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        repo.get_session(conn, 999)


def test_require_active_session_when_none(conn: sqlite3.Connection) -> None:
    with pytest.raises(StateError, match="No active session"):
        repo.require_active_session(conn)
