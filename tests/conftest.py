from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from poker import db
from poker.cli import app


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "poker.db"


@pytest.fixture
def conn(db_path: Path):
    connection = db.connect(db_path)
    yield connection
    connection.close()


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def invoke(runner: CliRunner, db_path: Path):
    def _invoke(*args: str, input: str | None = None):
        return runner.invoke(
            app,
            list(args),
            input=input,
            env={db.DB_ENV_VAR: str(db_path)},
            catch_exceptions=False,
        )

    return _invoke


def output_of(result) -> str:
    """Return combined output regardless of how the runner captures stderr."""
    output = result.output or ""
    stderr = getattr(result, "stderr", None) or ""
    if stderr and stderr not in output:
        return output + stderr
    return output
