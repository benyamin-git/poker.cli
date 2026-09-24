"""SQLite connection handling and schema migrations."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

DB_ENV_VAR = "POKERPOT_DB"

_MIGRATION_1 = (
    """
    CREATE TABLE players (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE COLLATE NOCASE,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE sessions (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL,
        status TEXT NOT NULL CHECK (status IN ('active', 'completed')),
        started_at TEXT NOT NULL,
        ended_at TEXT
    )
    """,
    """
    CREATE UNIQUE INDEX idx_sessions_single_active
        ON sessions (status) WHERE status = 'active'
    """,
    """
    CREATE TABLE session_players (
        session_id INTEGER NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
        player_id INTEGER NOT NULL REFERENCES players (id) ON DELETE CASCADE,
        PRIMARY KEY (session_id, player_id)
    )
    """,
    """
    CREATE TABLE rounds (
        id INTEGER PRIMARY KEY,
        session_id INTEGER NOT NULL REFERENCES sessions (id) ON DELETE CASCADE,
        number INTEGER NOT NULL CHECK (number > 0),
        created_at TEXT NOT NULL,
        UNIQUE (session_id, number)
    )
    """,
    "CREATE INDEX idx_rounds_session ON rounds (session_id)",
    """
    CREATE TABLE round_participants (
        id INTEGER PRIMARY KEY,
        round_id INTEGER NOT NULL REFERENCES rounds (id) ON DELETE CASCADE,
        player_id INTEGER NOT NULL REFERENCES players (id) ON DELETE RESTRICT,
        role TEXT NOT NULL CHECK (role IN ('winner', 'loser')),
        amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
        UNIQUE (round_id, player_id)
    )
    """,
    "CREATE INDEX idx_participants_round ON round_participants (round_id)",
    "CREATE INDEX idx_participants_player ON round_participants (player_id)",
)

MIGRATIONS: tuple[tuple[str, ...], ...] = (_MIGRATION_1,)


def default_db_path() -> Path:
    """Return the conventional database location."""
    data_home = os.environ.get("XDG_DATA_HOME")
    base = Path(data_home) if data_home else Path.home() / ".local" / "share"
    return base / "pokerpot" / "pokerpot.db"


def resolve_db_path(override: Path | None = None) -> Path:
    """Resolve the database path from an override, the environment or defaults."""
    if override is not None:
        return override.expanduser()
    env_path = os.environ.get(DB_ENV_VAR)
    if env_path:
        return Path(env_path).expanduser()
    return default_db_path()


def connect(path: Path) -> sqlite3.Connection:
    """Open (creating if needed) the database at ``path`` and migrate it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> None:
    """Apply pending migrations sequentially using ``PRAGMA user_version``."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for target, statements in enumerate(MIGRATIONS[version:], start=version + 1):
        for statement in statements:
            conn.execute(statement)
        conn.execute(f"PRAGMA user_version = {target}")
        conn.commit()
