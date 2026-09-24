from __future__ import annotations

import csv
import io
import json

from conftest import output_of


def _setup(invoke, *names: str) -> None:
    for name in names:
        assert invoke("player", "add", name).exit_code == 0
    assert invoke("session", "start", "--players", ",".join(names)).exit_code == 0


def _record(invoke, loser: str, winners: list[str]) -> None:
    args = ["round", "add", "--loser", loser]
    for winner in winners:
        args += ["--winner", winner]
    assert invoke(*args, "--yes").exit_code == 0


def _sample_session(invoke) -> None:
    _setup(invoke, "Ali", "Ben", "Reza")
    _record(invoke, "Ali=20", ["Ben"])
    _record(invoke, "Reza=30", ["Ben=15", "Ali=15"])


def test_export_text_default(invoke) -> None:
    _sample_session(invoke)
    result = invoke("session", "export")
    assert result.exit_code == 0
    assert "poker.cli session report" in result.output
    assert "\x1b" not in result.output
    assert "Checks" in result.output


def test_export_json(invoke) -> None:
    _sample_session(invoke)
    result = invoke("session", "export", "--format", "json")
    assert result.exit_code == 0
    document = json.loads(result.output)
    assert document["session"]["name"]
    assert len(document["rounds"]) == 2
    assert sum(entry["balance_cents"] for entry in document["standings"]) == 0


def test_export_csv(invoke) -> None:
    _sample_session(invoke)
    result = invoke("session", "export", "--format", "csv")
    assert result.exit_code == 0
    rows = list(csv.reader(io.StringIO(result.output)))
    assert rows[0] == ["round", "player", "role", "amount_cents", "amount"]
    assert len(rows) == 6


def test_export_to_file(invoke, tmp_path) -> None:
    _sample_session(invoke)
    target = tmp_path / "report.txt"
    result = invoke("session", "export", "--output", str(target))
    assert result.exit_code == 0
    assert target.exists()
    assert "poker.cli session report" in target.read_text(encoding="utf-8")


def test_export_completed_session_by_id(invoke) -> None:
    _sample_session(invoke)
    invoke("session", "end", "--yes")
    result = invoke("session", "export", "1")
    assert result.exit_code == 0
    assert "poker.cli session report" in result.output
    assert "Status:   completed" in result.output


def test_export_unknown_format(invoke) -> None:
    _sample_session(invoke)
    result = invoke("session", "export", "--format", "yaml")
    assert result.exit_code == 1
    assert "Unknown format" in output_of(result)


def test_export_without_session(invoke) -> None:
    result = invoke("session", "export")
    assert result.exit_code == 1
    assert "No active session" in output_of(result)


def test_history_lists_completed_sessions(invoke) -> None:
    _sample_session(invoke)
    result = invoke("history")
    assert result.exit_code == 0
    assert "No completed sessions yet" in result.output

    invoke("session", "end", "--yes")
    result = invoke("history")
    assert result.exit_code == 0
    assert "completed" in result.output
    assert "Session" in result.output
