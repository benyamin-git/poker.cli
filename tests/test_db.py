from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from poker import db, repo


def test_connect_creates_database_file(db_path: Path) -> None:
    assert not db_path.exists()
    conn = db.connect(db_path)
    assert db_path.exists()
    conn.close()


def test_connect_creates_parent_directories(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "data" / "poker.db"
    conn = db.connect(path)
    assert path.exists()
    conn.close()


def test_migration_sets_user_version(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1


def test_connect_is_idempotent(db_path: Path) -> None:
    db.connect(db_path).close()
    conn = db.connect(db_path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.close()


def test_foreign_keys_enabled(conn: sqlite3.Connection) -> None:
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_only_one_active_session_allowed(conn: sqlite3.Connection) -> None:
    now = repo.now_utc()
    with conn:
        conn.execute(
            "INSERT INTO sessions (name, status, started_at) VALUES ('a', 'active', ?)", (now,)
        )
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO sessions (name, status, started_at) VALUES ('b', 'active', ?)",
                (now,),
            )


def test_multiple_completed_sessions_allowed(conn: sqlite3.Connection) -> None:
    now = repo.now_utc()
    with conn:
        conn.execute(
            "INSERT INTO sessions (name, status, started_at, ended_at) "
            "VALUES ('a', 'completed', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO sessions (name, status, started_at, ended_at) "
            "VALUES ('b', 'completed', ?, ?)",
            (now, now),
        )
    assert conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 2


def _insert_session_round(conn: sqlite3.Connection) -> tuple[int, int]:
    now = repo.now_utc()
    with conn:
        session_id = conn.execute(
            "INSERT INTO sessions (name, status, started_at) VALUES ('s', 'active', ?)", (now,)
        ).lastrowid
        player_id = conn.execute(
            "INSERT INTO players (name, created_at) VALUES ('p', ?)", (now,)
        ).lastrowid
        round_id = conn.execute(
            "INSERT INTO rounds (session_id, number, created_at) VALUES (?, 1, ?)",
            (session_id, now),
        ).lastrowid
    return round_id, player_id


def test_round_participant_amount_must_be_positive(conn: sqlite3.Connection) -> None:
    round_id, player_id = _insert_session_round(conn)
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO round_participants (round_id, player_id, role, amount_cents) "
                "VALUES (?, ?, 'winner', 0)",
                (round_id, player_id),
            )


def test_round_participant_role_is_checked(conn: sqlite3.Connection) -> None:
    round_id, player_id = _insert_session_round(conn)
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO round_participants (round_id, player_id, role, amount_cents) "
                "VALUES (?, ?, 'spectator', 100)",
                (round_id, player_id),
            )


def test_player_with_round_cannot_be_deleted(conn: sqlite3.Connection) -> None:
    round_id, player_id = _insert_session_round(conn)
    with conn:
        conn.execute(
            "INSERT INTO round_participants (round_id, player_id, role, amount_cents) "
            "VALUES (?, ?, 'winner', 100)",
            (round_id, player_id),
        )
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("DELETE FROM players WHERE id = ?", (player_id,))


def test_resolve_db_path_prefers_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(db.DB_ENV_VAR, str(tmp_path / "env.db"))
    override = tmp_path / "override.db"
    assert db.resolve_db_path(override) == override
    assert db.resolve_db_path() == tmp_path / "env.db"
    monkeypatch.delenv(db.DB_ENV_VAR)
    assert db.resolve_db_path().name == "poker.db"


def test_default_db_path_uses_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    assert db.default_db_path() == tmp_path / "xdg" / "poker.cli" / "poker.db"
