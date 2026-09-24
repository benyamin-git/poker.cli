"""Command-line interface for PokerPot."""

from __future__ import annotations

import typer

from pokerpot import __version__

app = typer.Typer(
    name="pokerpot",
    help="Track poker-night money between friends: rounds, balances, settlement.",
    no_args_is_help=True,
    add_completion=False,
)


def _show_version(value: bool) -> None:
    if value:
        typer.echo(f"pokerpot {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(
        False,
        "--version",
        callback=_show_version,
        is_eager=True,
        help="Show the version and exit.",
    ),
) -> None:
    """PokerPot: a local-only CLI ledger for poker sessions."""
