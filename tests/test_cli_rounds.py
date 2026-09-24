from __future__ import annotations

from conftest import output_of


def _setup(invoke, *names: str) -> None:
    for name in names:
        assert invoke("player", "add", name).exit_code == 0
    assert invoke("session", "start", "--players", ",".join(names)).exit_code == 0


def test_round_add_basic(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", "add", "--loser", "Alice=20", "--winner", "Bob", "--yes")
    assert result.exit_code == 0
    assert "Recorded round 1" in result.output

    result = invoke("round", "list")
    assert result.exit_code == 0
    assert "Alice $20.00" in result.output
    assert "Bob $20.00" in result.output


def test_round_add_multi_losers_and_winners(invoke) -> None:
    _setup(invoke, "Alice", "Bob", "Carol")
    result = invoke(
        "round",
        "add",
        "--loser",
        "Alice=20",
        "--loser",
        "Bob=30",
        "--winner",
        "Carol",
        "--yes",
    )
    assert result.exit_code == 0
    result = invoke("round", "list")
    assert "Carol $50.00" in result.output


def test_round_add_equal_split_remainder(invoke) -> None:
    _setup(invoke, "Alice", "Bob", "Carol", "Dave")
    result = invoke(
        "round",
        "add",
        "--loser",
        "Alice=10",
        "--winner",
        "Bob",
        "--winner",
        "Carol",
        "--winner",
        "Dave",
        "--yes",
    )
    assert result.exit_code == 0
    result = invoke("round", "list")
    assert "Bob $3.34" in result.output
    assert "Carol $3.33" in result.output
    assert "Dave $3.33" in result.output


def test_round_add_custom_winner_amounts(invoke) -> None:
    _setup(invoke, "Alice", "Bob", "Carol")
    result = invoke(
        "round",
        "add",
        "--loser",
        "Alice=50",
        "--winner",
        "Bob=30",
        "--winner",
        "Carol=20",
        "--yes",
    )
    assert result.exit_code == 0
    result = invoke("round", "list")
    assert "Bob $30.00" in result.output
    assert "Carol $20.00" in result.output


def test_round_add_requires_active_session(invoke) -> None:
    result = invoke("round", "add", "--loser", "Alice=20", "--winner", "Bob", "--yes")
    assert result.exit_code == 1
    assert "No active session" in output_of(result)


def test_round_add_missing_winner(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", "add", "--loser", "Alice=20", "--yes")
    assert result.exit_code == 1
    assert "at least one --winner" in output_of(result)


def test_round_add_missing_loser(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", "add", "--winner", "Bob", "--yes")
    assert result.exit_code == 1
    assert "at least one --loser" in output_of(result)


def test_round_add_bad_loser_syntax(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", "add", "--loser", "Alice", "--winner", "Bob", "--yes")
    assert result.exit_code == 1
    assert "NAME=AMOUNT" in output_of(result)


def test_round_add_mixed_winner_amounts(invoke) -> None:
    _setup(invoke, "Alice", "Bob", "Carol")
    result = invoke(
        "round",
        "add",
        "--loser",
        "Alice=20",
        "--winner",
        "Bob=10",
        "--winner",
        "Carol",
        "--yes",
    )
    assert result.exit_code == 1
    assert "either all winners or none" in output_of(result)


def test_round_add_unbalanced_custom_split(invoke) -> None:
    _setup(invoke, "Alice", "Bob", "Carol")
    result = invoke(
        "round",
        "add",
        "--loser",
        "Alice=20",
        "--winner",
        "Bob=10",
        "--winner",
        "Carol=5",
        "--yes",
    )
    assert result.exit_code == 1
    assert "does not balance" in output_of(result)


def test_round_add_duplicate_loser(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke(
        "round", "add", "--loser", "Alice=10", "--loser", "Alice=10", "--winner", "Bob", "--yes"
    )
    assert result.exit_code == 1
    assert "twice" in output_of(result)


def test_round_add_player_not_in_session(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    invoke("player", "add", "Mallory")
    result = invoke("round", "add", "--loser", "Alice=20", "--winner", "Mallory", "--yes")
    assert result.exit_code == 1
    assert "not in session" in output_of(result)


def test_round_add_confirmation_can_cancel(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", "add", "--loser", "Alice=20", "--winner", "Bob", input="n\n")
    assert result.exit_code == 0
    assert "cancelled" in result.output
    result = invoke("round", "list")
    assert "No rounds recorded yet" in result.output


def test_round_interactive_basic(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", input="1\n20\nn\n1\n\n\n")
    assert result.exit_code == 0
    assert "Recorded round 1" in result.output
    result = invoke("round", "list")
    assert "Alice $20.00" in result.output
    assert "Bob $20.00" in result.output


def test_round_interactive_custom_split(invoke) -> None:
    _setup(invoke, "Alice", "Bob", "Carol")
    result = invoke("round", input="1\n30\nn\n1\ny\n1\nn\nn\n10\n20\n\n")
    assert result.exit_code == 0
    result = invoke("round", "list")
    assert "Bob $10.00" in result.output
    assert "Carol $20.00" in result.output


def test_round_interactive_creates_unknown_player(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", input="Dave\n\n20\nn\n1\n\n\n")
    assert result.exit_code == 0
    result = invoke("player", "list")
    assert "Dave" in result.output
    assert "Dave $20.00" in invoke("round", "list").output


def test_round_interactive_can_cancel(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", input="1\n20\nn\n1\n\nn\n")
    assert result.exit_code == 0
    assert "cancelled" in result.output
    assert "No rounds recorded yet" in invoke("round", "list").output


def test_round_undo_with_yes(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    invoke("round", "add", "--loser", "Alice=20", "--winner", "Bob", "--yes")
    result = invoke("round", "undo", "--yes")
    assert result.exit_code == 0
    assert "Removed round 1" in result.output
    assert "No rounds recorded yet" in invoke("round", "list").output


def test_round_undo_asks_for_confirmation(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    invoke("round", "add", "--loser", "Alice=20", "--winner", "Bob", "--yes")
    result = invoke("round", "undo", input="n\n")
    assert result.exit_code == 1
    assert "Alice $20.00" in invoke("round", "list").output


def test_round_undo_without_rounds(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    result = invoke("round", "undo", "--yes")
    assert result.exit_code == 1
    assert "no rounds to undo" in output_of(result)


def test_round_add_to_ended_session_fails(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    invoke("session", "end", "--yes")
    result = invoke("round", "add", "--loser", "Alice=20", "--winner", "Bob", "--yes")
    assert result.exit_code == 1
    assert "No active session" in output_of(result)


def test_session_show_rounds(invoke) -> None:
    _setup(invoke, "Alice", "Bob")
    invoke("round", "add", "--loser", "Alice=20", "--winner", "Bob", "--yes")
    result = invoke("session", "show", "--rounds")
    assert result.exit_code == 0
    assert "Losers" in result.output
    assert "Winners" in result.output
    assert "Alice $20.00" in result.output
