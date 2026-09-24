from __future__ import annotations

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


def _completed_night(invoke, name: str, loser: str, winners: list[str], players: str) -> None:
    assert invoke("session", "start", "--name", name, "--players", players).exit_code == 0
    _record(invoke, loser, winners)
    assert invoke("session", "end", "--yes").exit_code == 0


def test_stats_summary(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    _record(invoke, "Alice=20", ["Bob"])
    invoke("session", "end", "--yes")

    result = invoke("stats")
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output
    assert "100.0%" in result.output  # Bob won his only session
    assert "0.0%" in result.output  # Alice lost hers


def test_stats_detail(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    _record(invoke, "Alice=20", ["Bob"])
    invoke("session", "end", "--yes")

    result = invoke("stats", "Alice")
    assert result.exit_code == 0
    assert "Statistics for Alice" in result.output
    assert "Sessions played" in result.output
    assert "-$20.00" in result.output
    assert "Longest losing streak" in result.output
    assert "Best single-round win" in result.output


def test_stats_ignores_active_session(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    _record(invoke, "Alice=20", ["Bob"])
    result = invoke("stats", "Alice")
    assert result.exit_code == 0
    assert "Sessions played" in result.output
    assert "-$20.00" not in result.output
    assert "$0.00" in result.output


def test_stats_counts_after_session_ends(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    _record(invoke, "Alice=20", ["Bob"])
    invoke("session", "end", "--yes")
    result = invoke("stats", "Bob")
    assert result.exit_code == 0
    assert "+$20.00" in result.output
    assert "100.0%" in result.output


def test_stats_unknown_player(invoke) -> None:
    _setup(invoke, "Alice")
    result = invoke("stats", "Nobody")
    assert result.exit_code == 1
    assert "not found" in output_of(result)


def test_stats_without_players(invoke) -> None:
    result = invoke("stats")
    assert result.exit_code == 0
    assert "No players yet" in result.output
