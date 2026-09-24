from __future__ import annotations

from conftest import output_of


def _add_players(invoke, *names: str) -> None:
    for name in names:
        result = invoke("player", "add", name)
        assert result.exit_code == 0


def test_session_start_with_players_option(invoke) -> None:
    _add_players(invoke, "Alice", "Bob")
    result = invoke("session", "start", "--name", "Friday Poker", "--players", "Alice,Bob")
    assert result.exit_code == 0
    assert "Friday Poker" in result.output

    result = invoke("session", "list")
    assert "Friday Poker" in result.output
    assert "active" in result.output


def test_session_start_interactive_selection(invoke) -> None:
    _add_players(invoke, "Alice", "Bob")
    result = invoke("session", "start", input="1,2\n")
    assert result.exit_code == 0

    result = invoke("session", "show")
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Bob" in result.output


def test_session_start_interactive_creates_unknown_player(invoke) -> None:
    _add_players(invoke, "Alice")
    result = invoke("session", "start", input="1,Carol\ny\n")
    assert result.exit_code == 0
    result = invoke("player", "list")
    assert "Carol" in result.output


def test_session_start_while_active_fails(invoke) -> None:
    _add_players(invoke, "Alice", "Bob")
    invoke("session", "start", "--players", "Alice")
    result = invoke("session", "start", "--players", "Bob")
    assert result.exit_code == 1
    assert "already active" in output_of(result)


def test_session_start_unknown_player_fails(invoke) -> None:
    _add_players(invoke, "Alice")
    result = invoke("session", "start", "--players", "Alice,Ghost")
    assert result.exit_code == 1
    assert "not found" in output_of(result)


def test_session_show_unknown_id_fails(invoke) -> None:
    result = invoke("session", "show", "99")
    assert result.exit_code == 1
    assert "not found" in output_of(result)


def test_session_show_without_active_fails(invoke) -> None:
    result = invoke("session", "show")
    assert result.exit_code == 1
    assert "No active session" in output_of(result)


def test_session_add_and_remove_player(invoke) -> None:
    _add_players(invoke, "Alice")
    invoke("session", "start", "--players", "Alice")
    result = invoke("session", "add-player", "Bob")
    assert result.exit_code == 0
    assert "Created player" in result.output

    result = invoke("session", "show")
    assert "Bob" in result.output

    result = invoke("session", "remove-player", "Bob")
    assert result.exit_code == 0
    result = invoke("session", "show")
    assert "Bob" not in result.output


def test_session_add_player_duplicate_fails(invoke) -> None:
    _add_players(invoke, "Alice")
    invoke("session", "start", "--players", "Alice")
    result = invoke("session", "add-player", "Alice")
    assert result.exit_code == 1
    assert "already in this session" in output_of(result)


def test_session_end_and_reopen(invoke) -> None:
    _add_players(invoke, "Alice")
    invoke("session", "start", "--players", "Alice")
    result = invoke("session", "end", "--yes")
    assert result.exit_code == 0
    assert "ended" in result.output

    result = invoke("session", "end", "1", "--yes")
    assert result.exit_code == 1
    assert "already ended" in output_of(result)

    result = invoke("session", "reopen", "1")
    assert result.exit_code == 0
    assert "reopened" in result.output

    result = invoke("session", "list")
    assert "active" in result.output


def test_session_end_asks_for_confirmation(invoke) -> None:
    _add_players(invoke, "Alice")
    invoke("session", "start", "--players", "Alice")
    result = invoke("session", "end", input="n\n")
    assert result.exit_code == 1
    result = invoke("session", "list")
    assert "active" in result.output


def test_session_reopen_requires_valid_id(invoke) -> None:
    result = invoke("session", "reopen", "abc")
    assert result.exit_code == 1
    assert "Invalid session ID" in output_of(result)
