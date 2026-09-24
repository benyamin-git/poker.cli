from __future__ import annotations

from pathlib import Path

from conftest import output_of
from typer.testing import CliRunner

from poker import db
from poker.cli import app


def test_version(invoke) -> None:
    result = invoke("--version")
    assert result.exit_code == 0
    assert "poker.cli" in result.output


def test_player_add_list_show(invoke) -> None:
    result = invoke("player", "add", "Alice")
    assert result.exit_code == 0
    assert "Alice" in result.output

    result = invoke("player", "list")
    assert result.exit_code == 0
    assert "Alice" in result.output

    result = invoke("player", "show", "alice")
    assert result.exit_code == 0
    assert "Alice" in result.output
    assert "Sessions: 0" in result.output


def test_player_add_duplicate_fails(invoke) -> None:
    invoke("player", "add", "Alice")
    result = invoke("player", "add", "alice")
    assert result.exit_code == 1
    assert "already exists" in output_of(result)


def test_player_list_empty_message(invoke) -> None:
    result = invoke("player", "list")
    assert result.exit_code == 0
    assert "No players yet" in result.output


def test_player_rename(invoke) -> None:
    invoke("player", "add", "Alice")
    result = invoke("player", "rename", "Alice", "Alicia")
    assert result.exit_code == 0
    result = invoke("player", "show", "Alicia")
    assert result.exit_code == 0


def test_player_delete_aborts_without_confirmation(invoke) -> None:
    invoke("player", "add", "Alice")
    result = invoke("player", "delete", "Alice", input="n\n")
    assert result.exit_code == 1
    result = invoke("player", "list")
    assert "Alice" in result.output


def test_player_delete_with_yes(invoke) -> None:
    invoke("player", "add", "Alice")
    result = invoke("player", "delete", "Alice", "--yes")
    assert result.exit_code == 0
    result = invoke("player", "list")
    assert "No players yet" in result.output


def test_player_show_unknown_fails(invoke) -> None:
    result = invoke("player", "show", "Nobody")
    assert result.exit_code == 1
    assert "not found" in output_of(result)


def test_db_option_overrides_environment(runner: CliRunner, db_path: Path, tmp_path: Path) -> None:
    other = tmp_path / "other.db"
    result = runner.invoke(
        app,
        ["--db", str(other), "player", "add", "Alice"],
        env={db.DB_ENV_VAR: str(db_path)},
        catch_exceptions=False,
    )
    assert result.exit_code == 0
    assert other.exists()
    assert not db_path.exists()
