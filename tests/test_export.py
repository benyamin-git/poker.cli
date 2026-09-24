from __future__ import annotations

import csv
import io
import json
import sqlite3

import pytest

from pokerpot import repo
from pokerpot.export import ExportData, session_to_csv, session_to_json, session_to_text
from pokerpot.settlement import settle


@pytest.fixture
def data(conn: sqlite3.Connection) -> ExportData:
    ids = {name: repo.add_player(conn, name).id for name in ("Ali", "Ben", "Reza")}
    session = repo.start_session(conn, "Friday Poker", list(ids.values()))
    repo.add_round(conn, session.id, {ids["Ali"]: 2000}, {ids["Ben"]: 2000})
    repo.add_round(conn, session.id, {ids["Reza"]: 3000}, {ids["Ben"]: 1500, ids["Ali"]: 1500})
    session = repo.end_session(conn, session.id)
    players = repo.session_players(conn, session.id)
    balances = repo.session_balances(conn, session.id)
    return ExportData(
        session=session,
        players=players,
        rounds=repo.list_rounds(conn, session.id),
        balances=balances,
        transfers=settle(balances),
    )


def test_balances_are_reproducible(data: ExportData) -> None:
    assert sum(data.balances.values()) == 0
    assert data.transfers == [(3, 2, 3000), (1, 2, 500)]


def test_text_export_is_plain_and_complete(data: ExportData) -> None:
    text = session_to_text(data)
    assert "\x1b" not in text
    assert "PokerPot session report" in text
    assert "Session:  Friday Poker" in text
    assert "Round 1" in text
    assert "Round 2" in text
    assert "  Ali" in text
    assert "-$20.00" in text
    assert "+$20.00" in text
    assert "Pot: $30.00" in text
    assert "Final standings" in text
    assert "Total" in text
    assert "Settlement" in text
    assert "Ali -> Ben" in text
    assert "Reza -> Ben" in text
    assert "Total losses:   $50.00" in text
    assert "Total winnings: $50.00" in text
    assert "Balanced:       yes" in text
    assert not text.startswith(" ")


def test_text_export_marks_active_sessions(data: ExportData) -> None:
    active = ExportData(
        session=repo_active(data),
        players=data.players,
        rounds=data.rounds,
        balances=data.balances,
        transfers=data.transfers,
    )
    assert "still active" in session_to_text(active)


def repo_active(data: ExportData):
    from dataclasses import replace

    return replace(data.session, status="active", ended_at=None)


def test_json_export_structure(data: ExportData) -> None:
    document = json.loads(session_to_json(data))
    assert document["schema_version"] == 1
    assert document["session"]["name"] == "Friday Poker"
    assert document["session"]["status"] == "completed"
    assert [player["name"] for player in document["players"]] == ["Ali", "Ben", "Reza"]
    assert len(document["rounds"]) == 2
    first = document["rounds"][0]
    assert first["number"] == 1
    assert first["pot_cents"] == 2000
    assert first["losers"] == [{"player_id": 1, "player": "Ali", "amount_cents": 2000}]
    assert first["winners"] == [{"player_id": 2, "player": "Ben", "amount_cents": 2000}]
    assert {entry["player"]: entry["balance_cents"] for entry in document["standings"]} == {
        "Ali": -500,
        "Ben": 3500,
        "Reza": -3000,
    }
    assert document["settlement"] == [
        {
            "from_player_id": 3,
            "from": "Reza",
            "to_player_id": 2,
            "to": "Ben",
            "amount_cents": 3000,
        },
        {
            "from_player_id": 1,
            "from": "Ali",
            "to_player_id": 2,
            "to": "Ben",
            "amount_cents": 500,
        },
    ]


def test_csv_export_long_format(data: ExportData) -> None:
    rows = list(csv.reader(io.StringIO(session_to_csv(data))))
    assert rows[0] == ["round", "player", "role", "amount_cents", "amount"]
    assert rows[1:] == [
        ["1", "Ali", "loser", "2000", "20.00"],
        ["1", "Ben", "winner", "2000", "20.00"],
        ["2", "Reza", "loser", "3000", "30.00"],
        ["2", "Ali", "winner", "1500", "15.00"],
        ["2", "Ben", "winner", "1500", "15.00"],
    ]
