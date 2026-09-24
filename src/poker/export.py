"""Session exports: plain text, JSON and CSV.

The text report is deliberately ANSI-free so it can be copied into chat apps.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass

from poker.money import format_money
from poker.render import local_time
from poker.repo import Player, Round, Session, now_utc
from poker.settlement import Transfer

SCHEMA_VERSION = 1
FORMATS = ("text", "json", "csv")


@dataclass(frozen=True)
class ExportData:
    session: Session
    players: list[Player]
    rounds: list[Round]
    balances: dict[int, int]
    transfers: list[Transfer]


def _name_width(names: list[str], minimum: int = 4) -> int:
    return max((len(name) for name in names), default=minimum)


def _plain_amount(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    value = abs(cents)
    return f"{sign}{value // 100}.{value % 100:02d}"


def session_to_text(data: ExportData) -> str:
    """Render a verification-friendly plain-text report."""
    session = data.session
    names = {player.id: player.name for player in data.players}
    title = "poker.cli session report"
    lines = [title, "=" * len(title), ""]
    lines.append(f"Session:  {session.name}")
    lines.append(f"ID:       {session.id}")
    lines.append(f"Status:   {session.status}")
    lines.append(f"Started:  {local_time(session.started_at)}")
    lines.append(f"Ended:    {local_time(session.ended_at) if session.ended_at else '-'}")
    lines.append(f"Players:  {', '.join(player.name for player in data.players) or '-'}")
    lines.append(f"Rounds:   {session.round_count}")
    if session.status != "completed":
        lines.append("")
        lines.append("Note: this session is still active; the settlement below is projected.")
    lines.append("")

    lines.append("Rounds")
    lines.append("------")
    lines.append("")
    if data.rounds:
        width = _name_width([p.player_name for round_ in data.rounds for p in round_.participants])
        for round_ in data.rounds:
            lines.append(f"Round {round_.number}")
            for participant in round_.participants:
                signed = (
                    participant.amount_cents
                    if participant.role == "winner"
                    else -participant.amount_cents
                )
                lines.append(
                    f"  {participant.player_name.ljust(width)}  "
                    f"{format_money(signed, plus=True).rjust(10)}"
                )
            lines.append(f"  Pot: {format_money(round_.pot_cents)}")
            lines.append("")
    else:
        lines.append("No rounds recorded.")
        lines.append("")

    lines.append("Final standings")
    lines.append("---------------")
    lines.append("")
    width = _name_width([player.name for player in data.players])
    standings = sorted(
        ((player.name, data.balances.get(player.id, 0)) for player in data.players),
        key=lambda item: (-item[1], item[0].lower()),
    )
    for name, balance in standings:
        lines.append(f"{name.ljust(width)}  {format_money(balance, plus=True).rjust(10)}")
    total = sum(data.balances.values())
    lines.append(f"{'Total'.ljust(width)}  {format_money(total, plus=True).rjust(10)}")
    lines.append("")

    lines.append("Settlement")
    lines.append("----------")
    lines.append("")
    if data.transfers:
        labels = [f"{names[from_id]} -> {names[to_id]}" for from_id, to_id, _ in data.transfers]
        label_width = max(len(label) for label in labels)
        for (_, _, amount), label in zip(data.transfers, labels, strict=True):
            lines.append(f"{label.ljust(label_width)}  {format_money(amount)}")
    else:
        lines.append("All settled up.")
    lines.append("")

    total_losses = sum(
        participant.amount_cents
        for round_ in data.rounds
        for participant in round_.participants
        if participant.role == "loser"
    )
    total_winnings = sum(round_.pot_cents for round_ in data.rounds)
    lines.append("Checks")
    lines.append("------")
    lines.append("")
    lines.append(f"Total losses:   {format_money(total_losses)}")
    lines.append(f"Total winnings: {format_money(total_winnings)}")
    lines.append(f"Balanced:       {'yes' if total_losses == total_winnings else 'NO'}")
    return "\n".join(lines) + "\n"


def session_to_json(data: ExportData) -> str:
    """Render a machine-readable session document."""
    session = data.session
    names = {player.id: player.name for player in data.players}
    document = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": now_utc(),
        "session": {
            "id": session.id,
            "name": session.name,
            "status": session.status,
            "started_at": session.started_at,
            "ended_at": session.ended_at,
        },
        "players": [{"id": player.id, "name": player.name} for player in data.players],
        "rounds": [
            {
                "number": round_.number,
                "created_at": round_.created_at,
                "pot_cents": round_.pot_cents,
                "losers": [
                    {
                        "player_id": participant.player_id,
                        "player": participant.player_name,
                        "amount_cents": participant.amount_cents,
                    }
                    for participant in round_.losers
                ],
                "winners": [
                    {
                        "player_id": participant.player_id,
                        "player": participant.player_name,
                        "amount_cents": participant.amount_cents,
                    }
                    for participant in round_.winners
                ],
            }
            for round_ in data.rounds
        ],
        "standings": [
            {
                "player_id": player.id,
                "player": player.name,
                "balance_cents": data.balances.get(player.id, 0),
            }
            for player in data.players
        ],
        "settlement": [
            {
                "from_player_id": from_id,
                "from": names[from_id],
                "to_player_id": to_id,
                "to": names[to_id],
                "amount_cents": amount,
            }
            for from_id, to_id, amount in data.transfers
        ],
    }
    return json.dumps(document, indent=2) + "\n"


def session_to_csv(data: ExportData) -> str:
    """Render the ledger in long format: one row per round participant."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["round", "player", "role", "amount_cents", "amount"])
    for round_ in data.rounds:
        for participant in round_.participants:
            writer.writerow(
                [
                    round_.number,
                    participant.player_name,
                    participant.role,
                    participant.amount_cents,
                    _plain_amount(participant.amount_cents),
                ]
            )
    return buffer.getvalue()
