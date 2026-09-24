from __future__ import annotations

import sqlite3

import pytest

from poker import repo
from poker.errors import ConflictError, NotFoundError, ValidationError


def test_add_and_get_by_name_and_id(conn: sqlite3.Connection) -> None:
    player = repo.add_player(conn, "Alice")
    assert player.name == "Alice"
    assert repo.get_player(conn, "alice").id == player.id
    assert repo.get_player(conn, str(player.id)).name == "Alice"


def test_names_are_case_insensitively_unique(conn: sqlite3.Connection) -> None:
    repo.add_player(conn, "Alice")
    with pytest.raises(ConflictError):
        repo.add_player(conn, "alice")


def test_name_whitespace_is_collapsed(conn: sqlite3.Connection) -> None:
    player = repo.add_player(conn, "  Alice   Smith  ")
    assert player.name == "Alice Smith"


@pytest.mark.parametrize("name", ["", "   ", "3", "000"])
def test_invalid_names_rejected(conn: sqlite3.Connection, name: str) -> None:
    with pytest.raises(ValidationError):
        repo.add_player(conn, name)


def test_long_name_rejected(conn: sqlite3.Connection) -> None:
    with pytest.raises(ValidationError):
        repo.add_player(conn, "x" * (repo.MAX_NAME_LENGTH + 1))


def test_list_players_sorted_by_name(conn: sqlite3.Connection) -> None:
    for name in ("Carol", "alice", "Bob"):
        repo.add_player(conn, name)
    assert [player.name for player in repo.list_players(conn)] == ["alice", "Bob", "Carol"]


def test_rename_keeps_id_and_history_counts(conn: sqlite3.Connection) -> None:
    player = repo.add_player(conn, "Alice")
    renamed = repo.rename_player(conn, "Alice", "Alicia")
    assert renamed.id == player.id
    assert renamed.name == "Alicia"
    assert repo.get_player(conn, str(player.id)).name == "Alicia"


def test_rename_to_existing_name_conflicts(conn: sqlite3.Connection) -> None:
    repo.add_player(conn, "Alice")
    repo.add_player(conn, "Bob")
    with pytest.raises(ConflictError):
        repo.rename_player(conn, "Alice", "bob")


def test_rename_unknown_player(conn: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        repo.rename_player(conn, "Nobody", "Someone")


def test_get_unknown_player(conn: sqlite3.Connection) -> None:
    with pytest.raises(NotFoundError):
        repo.get_player(conn, "Nobody")
    with pytest.raises(NotFoundError):
        repo.get_player(conn, "42")


def test_delete_unused_player(conn: sqlite3.Connection) -> None:
    repo.add_player(conn, "Alice")
    deleted = repo.delete_player(conn, "Alice")
    assert deleted.name == "Alice"
    assert repo.list_players(conn) == []


def test_delete_player_with_rounds_is_refused(conn: sqlite3.Connection) -> None:
    player = repo.add_player(conn, "Alice")
    now = repo.now_utc()
    with conn:
        session_id = conn.execute(
            "INSERT INTO sessions (name, status, started_at) VALUES ('s', 'active', ?)", (now,)
        ).lastrowid
        round_id = conn.execute(
            "INSERT INTO rounds (session_id, number, created_at) VALUES (?, 1, ?)",
            (session_id, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO round_participants (round_id, player_id, role, amount_cents) "
            "VALUES (?, ?, 'winner', 100)",
            (round_id, player.id),
        )
    with pytest.raises(ConflictError, match="recorded round"):
        repo.delete_player(conn, "Alice")


def test_player_counts_are_reported(conn: sqlite3.Connection) -> None:
    player = repo.add_player(conn, "Alice")
    now = repo.now_utc()
    with conn:
        session_id = conn.execute(
            "INSERT INTO sessions (name, status, started_at) VALUES ('s', 'active', ?)", (now,)
        ).lastrowid
        conn.execute(
            "INSERT INTO session_players (session_id, player_id) VALUES (?, ?)",
            (session_id, player.id),
        )
        round_id = conn.execute(
            "INSERT INTO rounds (session_id, number, created_at) VALUES (?, 1, ?)",
            (session_id, now),
        ).lastrowid
        conn.execute(
            "INSERT INTO round_participants (round_id, player_id, role, amount_cents) "
            "VALUES (?, ?, 'winner', 100)",
            (round_id, player.id),
        )
    found = repo.get_player(conn, "Alice")
    assert found.session_count == 1
    assert found.round_count == 1
