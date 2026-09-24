from __future__ import annotations

import sqlite3

import pytest

from poker import repo


@pytest.fixture
def players_and_session(conn: sqlite3.Connection) -> tuple[dict[str, int], repo.Session]:
    ids = {name: repo.add_player(conn, name).id for name in ("Alice", "Bob", "Carol")}
    session = repo.start_session(conn, "Test", list(ids.values()))
    return ids, session


def test_balances_start_at_zero(
    conn: sqlite3.Connection, players_and_session: tuple[dict[str, int], repo.Session]
) -> None:
    ids, session = players_and_session
    balances = repo.session_balances(conn, session.id)
    assert balances == {ids["Alice"]: 0, ids["Bob"]: 0, ids["Carol"]: 0}


def test_balances_accumulate_over_rounds(
    conn: sqlite3.Connection, players_and_session: tuple[dict[str, int], repo.Session]
) -> None:
    ids, session = players_and_session
    repo.add_round(conn, session.id, {ids["Alice"]: 2000}, {ids["Bob"]: 2000})
    repo.add_round(conn, session.id, {ids["Bob"]: 3000}, {ids["Alice"]: 1000, ids["Carol"]: 2000})
    balances = repo.session_balances(conn, session.id)
    assert balances == {ids["Alice"]: -1000, ids["Bob"]: -1000, ids["Carol"]: 2000}
    assert sum(balances.values()) == 0


def test_balances_include_players_without_rounds(
    conn: sqlite3.Connection, players_and_session: tuple[dict[str, int], repo.Session]
) -> None:
    ids, session = players_and_session
    repo.add_round(conn, session.id, {ids["Alice"]: 500}, {ids["Bob"]: 500})
    balances = repo.session_balances(conn, session.id)
    assert balances[ids["Carol"]] == 0


def test_balances_reflect_undo(
    conn: sqlite3.Connection, players_and_session: tuple[dict[str, int], repo.Session]
) -> None:
    ids, session = players_and_session
    repo.add_round(conn, session.id, {ids["Alice"]: 2000}, {ids["Bob"]: 2000})
    repo.undo_last_round(conn, session.id)
    assert repo.session_balances(conn, session.id) == {
        ids["Alice"]: 0,
        ids["Bob"]: 0,
        ids["Carol"]: 0,
    }
