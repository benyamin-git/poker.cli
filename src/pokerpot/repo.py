"""Typed data access for players, sessions and rounds."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from pokerpot.errors import ConflictError, NotFoundError, ValidationError

MAX_NAME_LENGTH = 40

_PLAYER_COLUMNS = """
    p.id, p.name, p.created_at,
    (SELECT COUNT(*) FROM session_players sp WHERE sp.player_id = p.id) AS session_count,
    (SELECT COUNT(*) FROM round_participants rp WHERE rp.player_id = p.id) AS round_count
"""


@dataclass(frozen=True)
class Player:
    id: int
    name: str
    created_at: str
    session_count: int = 0
    round_count: int = 0


def now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _clean_name(name: str) -> str:
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValidationError("Player name cannot be empty.")
    if len(cleaned) > MAX_NAME_LENGTH:
        raise ValidationError(f"Player name cannot be longer than {MAX_NAME_LENGTH} characters.")
    if cleaned.isdigit():
        raise ValidationError(
            "Player names cannot be only digits, because they would be confused with player IDs."
        )
    return cleaned


def _player_from_row(row: sqlite3.Row) -> Player:
    return Player(
        id=row["id"],
        name=row["name"],
        created_at=row["created_at"],
        session_count=row["session_count"],
        round_count=row["round_count"],
    )


def add_player(conn: sqlite3.Connection, name: str) -> Player:
    """Create a player and return it."""
    cleaned = _clean_name(name)
    created_at = now_utc()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO players (name, created_at) VALUES (?, ?)",
                (cleaned, created_at),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"Player {cleaned!r} already exists.") from exc
    return Player(id=cursor.lastrowid, name=cleaned, created_at=created_at)


def list_players(conn: sqlite3.Connection) -> list[Player]:
    """Return all players ordered by name."""
    rows = conn.execute(
        f"SELECT {_PLAYER_COLUMNS} FROM players p ORDER BY p.name COLLATE NOCASE"
    ).fetchall()
    return [_player_from_row(row) for row in rows]


def get_player(conn: sqlite3.Connection, ref: str) -> Player:
    """Look up a player by numeric ID or case-insensitive name."""
    ref = ref.strip()
    if ref.isdigit():
        query = f"SELECT {_PLAYER_COLUMNS} FROM players p WHERE p.id = ?"
        params: tuple[object, ...] = (int(ref),)
    else:
        query = f"SELECT {_PLAYER_COLUMNS} FROM players p WHERE p.name = ? COLLATE NOCASE"
        params = (ref,)
    row = conn.execute(query, params).fetchone()
    if row is None:
        raise NotFoundError(f"Player {ref!r} not found.")
    return _player_from_row(row)


def rename_player(conn: sqlite3.Connection, ref: str, new_name: str) -> Player:
    """Rename a player, keeping all history attached."""
    player = get_player(conn, ref)
    cleaned = _clean_name(new_name)
    try:
        with conn:
            conn.execute("UPDATE players SET name = ? WHERE id = ?", (cleaned, player.id))
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"Player {cleaned!r} already exists.") from exc
    return get_player(conn, str(player.id))


def delete_player(conn: sqlite3.Connection, ref: str) -> Player:
    """Delete a player that has no recorded rounds."""
    player = get_player(conn, ref)
    if player.round_count:
        raise ConflictError(
            f"Player {player.name!r} is part of {player.round_count} recorded round(s) "
            "and cannot be deleted. Rename the player instead."
        )
    with conn:
        conn.execute("DELETE FROM players WHERE id = ?", (player.id,))
    return player
