"""Typed data access for players, sessions and rounds."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime

from pokerpot import accounting
from pokerpot.accounting import validate_round
from pokerpot.errors import ConflictError, NotFoundError, StateError, ValidationError

MAX_NAME_LENGTH = 40
MAX_SESSION_NAME_LENGTH = 60

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


@dataclass(frozen=True)
class Session:
    id: int
    name: str
    status: str
    started_at: str
    ended_at: str | None
    player_count: int = 0
    round_count: int = 0


@dataclass(frozen=True)
class Participant:
    player_id: int
    player_name: str
    role: str
    amount_cents: int


@dataclass(frozen=True)
class Round:
    id: int
    session_id: int
    number: int
    created_at: str
    participants: tuple[Participant, ...]

    @property
    def pot_cents(self) -> int:
        return sum(p.amount_cents for p in self.participants if p.role == "winner")

    @property
    def losers(self) -> tuple[Participant, ...]:
        return tuple(p for p in self.participants if p.role == "loser")

    @property
    def winners(self) -> tuple[Participant, ...]:
        return tuple(p for p in self.participants if p.role == "winner")


def now_utc() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def clean_player_name(name: str) -> str:
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
    cleaned = clean_player_name(name)
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
    cleaned = clean_player_name(new_name)
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


_SESSION_COLUMNS = """
    s.id, s.name, s.status, s.started_at, s.ended_at,
    (SELECT COUNT(*) FROM session_players sp WHERE sp.session_id = s.id) AS player_count,
    (SELECT COUNT(*) FROM rounds r WHERE r.session_id = s.id) AS round_count
"""


def default_session_name() -> str:
    """Return the local-time default name for a new session."""
    return datetime.now().astimezone().strftime("Session %Y-%m-%d %H:%M")


def _clean_session_name(name: str | None) -> str:
    if name is None:
        return default_session_name()
    cleaned = " ".join(name.split())
    if not cleaned:
        raise ValidationError("Session name cannot be empty.")
    if len(cleaned) > MAX_SESSION_NAME_LENGTH:
        raise ValidationError(
            f"Session name cannot be longer than {MAX_SESSION_NAME_LENGTH} characters."
        )
    return cleaned


def _session_from_row(row: sqlite3.Row) -> Session:
    return Session(
        id=row["id"],
        name=row["name"],
        status=row["status"],
        started_at=row["started_at"],
        ended_at=row["ended_at"],
        player_count=row["player_count"],
        round_count=row["round_count"],
    )


def get_active_session(conn: sqlite3.Connection) -> Session | None:
    """Return the currently active session, if any."""
    row = conn.execute(
        f"SELECT {_SESSION_COLUMNS} FROM sessions s WHERE s.status = 'active'"
    ).fetchone()
    return _session_from_row(row) if row else None


def require_active_session(conn: sqlite3.Connection) -> Session:
    """Return the active session or raise a state error."""
    session = get_active_session(conn)
    if session is None:
        raise StateError("No active session. Start one with: pokerpot session start")
    return session


def get_session(conn: sqlite3.Connection, session_id: int) -> Session:
    """Look up a session by ID."""
    row = conn.execute(
        f"SELECT {_SESSION_COLUMNS} FROM sessions s WHERE s.id = ?", (session_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Session {session_id} not found.")
    return _session_from_row(row)


def list_sessions(conn: sqlite3.Connection, status: str | None = None) -> list[Session]:
    """Return sessions, active first, newest first."""
    query = f"SELECT {_SESSION_COLUMNS} FROM sessions s"
    params: tuple[object, ...] = ()
    if status is not None:
        query += " WHERE s.status = ?"
        params = (status,)
    query += " ORDER BY (s.status = 'active') DESC, s.started_at DESC, s.id DESC"
    return [_session_from_row(row) for row in conn.execute(query, params).fetchall()]


def start_session(conn: sqlite3.Connection, name: str | None, player_ids: list[int]) -> Session:
    """Start a new session with the given players."""
    if get_active_session(conn) is not None:
        raise StateError("A session is already active. End it first with: pokerpot session end")
    cleaned = _clean_session_name(name)
    unique_ids = list(dict.fromkeys(player_ids))
    if not unique_ids:
        raise ValidationError("A session needs at least one player.")
    players = [get_player(conn, str(player_id)) for player_id in unique_ids]
    try:
        with conn:
            session_id = conn.execute(
                "INSERT INTO sessions (name, status, started_at) VALUES (?, 'active', ?)",
                (cleaned, now_utc()),
            ).lastrowid
            conn.executemany(
                "INSERT INTO session_players (session_id, player_id) VALUES (?, ?)",
                [(session_id, player.id) for player in players],
            )
    except sqlite3.IntegrityError as exc:
        raise StateError(
            "A session is already active. End it first with: pokerpot session end"
        ) from exc
    return get_session(conn, session_id)


def session_players(conn: sqlite3.Connection, session_id: int) -> list[Player]:
    """Return the players of a session, ordered by name."""
    rows = conn.execute(
        f"""
        SELECT {_PLAYER_COLUMNS}
        FROM session_players sp
        JOIN players p ON p.id = sp.player_id
        WHERE sp.session_id = ?
        ORDER BY p.name COLLATE NOCASE
        """,
        (session_id,),
    ).fetchall()
    return [_player_from_row(row) for row in rows]


def add_session_player(conn: sqlite3.Connection, session_id: int, ref: str) -> tuple[Player, bool]:
    """Add a player to an active session, creating the player if needed."""
    session = get_session(conn, session_id)
    if session.status != "active":
        raise StateError(
            f"Session {session.name!r} has ended. Reopen it with: "
            f"pokerpot session reopen {session.id}"
        )
    created = False
    try:
        player = get_player(conn, ref)
    except NotFoundError:
        player = add_player(conn, ref)
        created = True
    try:
        with conn:
            conn.execute(
                "INSERT INTO session_players (session_id, player_id) VALUES (?, ?)",
                (session.id, player.id),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError(f"Player {player.name!r} is already in this session.") from exc
    return player, created


def remove_session_player(conn: sqlite3.Connection, session_id: int, ref: str) -> Player:
    """Remove a player from an active session if they have no rounds there."""
    session = get_session(conn, session_id)
    if session.status != "active":
        raise StateError(
            f"Session {session.name!r} has ended. Reopen it with: "
            f"pokerpot session reopen {session.id}"
        )
    player = get_player(conn, ref)
    in_session = conn.execute(
        "SELECT 1 FROM session_players WHERE session_id = ? AND player_id = ?",
        (session.id, player.id),
    ).fetchone()
    if in_session is None:
        raise NotFoundError(f"Player {player.name!r} is not in session {session.name!r}.")
    rounds_played = conn.execute(
        """
        SELECT COUNT(*)
        FROM round_participants rp
        JOIN rounds r ON r.id = rp.round_id
        WHERE r.session_id = ? AND rp.player_id = ?
        """,
        (session.id, player.id),
    ).fetchone()[0]
    if rounds_played:
        raise ConflictError(
            f"Player {player.name!r} has {rounds_played} recorded round(s) in this "
            "session and cannot be removed."
        )
    with conn:
        conn.execute(
            "DELETE FROM session_players WHERE session_id = ? AND player_id = ?",
            (session.id, player.id),
        )
    return player


def end_session(conn: sqlite3.Connection, session_id: int) -> Session:
    """Mark a session as completed."""
    session = get_session(conn, session_id)
    if session.status == "completed":
        raise StateError(f"Session {session.name!r} has already ended.")
    with conn:
        conn.execute(
            "UPDATE sessions SET status = 'completed', ended_at = ? WHERE id = ?",
            (now_utc(), session.id),
        )
    return get_session(conn, session.id)


def reopen_session(conn: sqlite3.Connection, session_id: int) -> Session:
    """Reopen a completed session so it can be corrected."""
    session = get_session(conn, session_id)
    if session.status == "active":
        raise StateError(f"Session {session.name!r} is already active.")
    active = get_active_session(conn)
    if active is not None:
        raise StateError(
            f"Session {active.name!r} is still active. End it first with: pokerpot session end"
        )
    with conn:
        conn.execute(
            "UPDATE sessions SET status = 'active', ended_at = NULL WHERE id = ?",
            (session.id,),
        )
    return get_session(conn, session.id)


def _session_player_ids(conn: sqlite3.Connection, session_id: int) -> set[int]:
    rows = conn.execute(
        "SELECT player_id FROM session_players WHERE session_id = ?", (session_id,)
    ).fetchall()
    return {row["player_id"] for row in rows}


def next_round_number(conn: sqlite3.Connection, session_id: int) -> int:
    """Return the next round number, reusing numbers freed by undo."""
    row = conn.execute(
        "SELECT COALESCE(MAX(number), 0) + 1 FROM rounds WHERE session_id = ?",
        (session_id,),
    ).fetchone()
    return int(row[0])


def _round_from_row(row: sqlite3.Row, participants: list[Participant]) -> Round:
    return Round(
        id=row["id"],
        session_id=row["session_id"],
        number=row["number"],
        created_at=row["created_at"],
        participants=tuple(participants),
    )


def _round_participants(conn: sqlite3.Connection, round_id: int) -> list[Participant]:
    rows = conn.execute(
        """
        SELECT rp.player_id, p.name AS player_name, rp.role, rp.amount_cents
        FROM round_participants rp
        JOIN players p ON p.id = rp.player_id
        WHERE rp.round_id = ?
        ORDER BY (rp.role = 'winner'), p.name COLLATE NOCASE
        """,
        (round_id,),
    ).fetchall()
    return [
        Participant(
            player_id=row["player_id"],
            player_name=row["player_name"],
            role=row["role"],
            amount_cents=row["amount_cents"],
        )
        for row in rows
    ]


def get_round(conn: sqlite3.Connection, round_id: int) -> Round:
    """Look up a round by ID."""
    row = conn.execute("SELECT * FROM rounds WHERE id = ?", (round_id,)).fetchone()
    if row is None:
        raise NotFoundError(f"Round {round_id} not found.")
    return _round_from_row(row, _round_participants(conn, round_id))


def add_round(
    conn: sqlite3.Connection,
    session_id: int,
    loser_amounts: dict[int, int],
    winner_amounts: dict[int, int],
) -> Round:
    """Validate and record one round atomically."""
    session = get_session(conn, session_id)
    if session.status != "active":
        raise StateError(
            f"Session {session.name!r} has ended. Reopen it with: "
            f"pokerpot session reopen {session.id}"
        )
    validate_round(loser_amounts, winner_amounts)
    roster = _session_player_ids(conn, session_id)
    for player_id in (*loser_amounts, *winner_amounts):
        if player_id not in roster:
            player = get_player(conn, str(player_id))
            raise ValidationError(f"Player {player.name!r} is not in session {session.name!r}.")
    number = next_round_number(conn, session_id)
    created_at = now_utc()
    rows = [(player_id, "loser", amount) for player_id, amount in loser_amounts.items()] + [
        (player_id, "winner", amount) for player_id, amount in winner_amounts.items()
    ]
    with conn:
        round_id = conn.execute(
            "INSERT INTO rounds (session_id, number, created_at) VALUES (?, ?, ?)",
            (session_id, number, created_at),
        ).lastrowid
        conn.executemany(
            "INSERT INTO round_participants (round_id, player_id, role, amount_cents) "
            "VALUES (?, ?, ?, ?)",
            [(round_id, player_id, role, amount) for player_id, role, amount in rows],
        )
    return get_round(conn, round_id)


def list_rounds(conn: sqlite3.Connection, session_id: int) -> list[Round]:
    """Return all rounds of a session in order."""
    rows = conn.execute(
        "SELECT * FROM rounds WHERE session_id = ? ORDER BY number", (session_id,)
    ).fetchall()
    return [_round_from_row(row, _round_participants(conn, row["id"])) for row in rows]


def session_balances(conn: sqlite3.Connection, session_id: int) -> dict[int, int]:
    """Compute every session player's net cents from the recorded rounds."""
    player_ids = [player.id for player in session_players(conn, session_id)]
    rounds = [
        [(p.player_id, p.role, p.amount_cents) for p in round_.participants]
        for round_ in list_rounds(conn, session_id)
    ]
    return accounting.session_balances(player_ids, rounds)


def last_round(conn: sqlite3.Connection, session_id: int) -> Round | None:
    """Return the most recently recorded round, if any."""
    row = conn.execute(
        "SELECT * FROM rounds WHERE session_id = ? ORDER BY number DESC LIMIT 1",
        (session_id,),
    ).fetchone()
    if row is None:
        return None
    return _round_from_row(row, _round_participants(conn, row["id"]))


def undo_last_round(conn: sqlite3.Connection, session_id: int) -> Round:
    """Delete the most recent round of an active session."""
    session = get_session(conn, session_id)
    if session.status != "active":
        raise StateError(
            f"Session {session.name!r} has ended. Reopen it with: "
            f"pokerpot session reopen {session.id}"
        )
    round_ = last_round(conn, session_id)
    if round_ is None:
        raise StateError("There are no rounds to undo in this session.")
    with conn:
        conn.execute("DELETE FROM rounds WHERE id = ?", (round_.id,))
    return round_
