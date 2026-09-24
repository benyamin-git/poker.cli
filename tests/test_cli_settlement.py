from __future__ import annotations


def _setup(invoke, *names: str) -> None:
    for name in names:
        assert invoke("player", "add", name).exit_code == 0
    assert invoke("session", "start", "--players", ",".join(names)).exit_code == 0


def _record(invoke, loser: str, winners: list[str]) -> None:
    args = ["round", "add", "--loser", loser]
    for winner in winners:
        args += ["--winner", winner]
    assert invoke(*args, "--yes").exit_code == 0


def _plan_example(invoke) -> None:
    # Ali -80, Ben +45, Reza +35, Sara 0
    _setup(invoke, "Ali", "Ben", "Reza", "Sara")
    _record(invoke, "Ali=20", ["Ben"])
    _record(invoke, "Ali=30", ["Reza"])
    _record(invoke, "Ali=30", ["Ben=25", "Reza=5"])


def test_session_show_balances(invoke) -> None:
    _plan_example(invoke)
    result = invoke("session", "show")
    assert result.exit_code == 0
    assert "Ali" in result.output
    assert "-$80.00" in result.output
    assert "+$45.00" in result.output
    assert "+$35.00" in result.output
    assert "$0.00" in result.output  # Sara and the total
    assert "Total" in result.output


def test_session_show_projected_settlement(invoke) -> None:
    _plan_example(invoke)
    result = invoke("session", "show", "--settlement")
    assert result.exit_code == 0
    assert "Projected settlement" in result.output
    assert "Ali" in result.output
    assert "Ben" in result.output
    assert "Reza" in result.output
    assert "$45.00" in result.output
    assert "$35.00" in result.output


def test_session_end_shows_standings_and_settlement(invoke) -> None:
    _plan_example(invoke)
    result = invoke("session", "end", "--yes")
    assert result.exit_code == 0
    assert "Final standings" in result.output
    assert "Settlement" in result.output
    assert "+$45.00" in result.output
    assert "$35.00" in result.output


def test_completed_session_settlement(invoke) -> None:
    _plan_example(invoke)
    invoke("session", "end", "--yes")
    result = invoke("session", "show", "1", "--settlement")
    assert result.exit_code == 0
    assert "Settlement" in result.output
    assert "Projected" not in result.output


def test_settled_session_shows_nothing_to_settle(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    _record(invoke, "Alice=20", ["Bob"])
    _record(invoke, "Bob=20", ["Alice"])
    result = invoke("session", "end", "--yes")
    assert result.exit_code == 0
    assert "All settled up." in result.output


def test_settlement_preview_before_any_rounds(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("session", "show", "--settlement")
    assert result.exit_code == 0
    assert "All settled up." in result.output
