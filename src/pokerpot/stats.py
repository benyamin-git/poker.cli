"""Accounting statistics for players.

PokerPot only records money movements (who lost what, who won the pot). These
statistics are honest about that: they measure results, never poker skill.
Break-even sessions count in the win-rate denominator and reset streaks.
"""

from __future__ import annotations

from dataclasses import dataclass

from pokerpot.repo import Round, Session


@dataclass(frozen=True)
class SessionRecord:
    session: Session
    player_ids: list[int]
    rounds: list[Round]


@dataclass(frozen=True)
class PlayerStats:
    player_id: int
    sessions_played: int
    total_net_cents: int
    total_won_cents: int
    total_lost_cents: int
    profitable_sessions: int
    losing_sessions: int
    break_even_sessions: int
    rounds_played: int
    rounds_won: int
    rounds_lost: int
    total_round_won_cents: int
    total_round_lost_cents: int
    average_session_cents: int
    median_session_cents: int
    best_session_cents: int | None
    worst_session_cents: int | None
    best_round_win_cents: int | None
    worst_round_loss_cents: int | None
    average_winning_round_cents: int | None
    average_losing_round_cents: int | None
    longest_winning_streak: int
    longest_losing_streak: int

    @property
    def session_win_rate(self) -> float:
        if not self.sessions_played:
            return 0.0
        return self.profitable_sessions / self.sessions_played

    @property
    def round_win_rate(self) -> float:
        if not self.rounds_played:
            return 0.0
        return self.rounds_won / self.rounds_played


def round_div(numerator: int, denominator: int) -> int:
    """Integer division rounded half away from zero."""
    if denominator == 0:
        raise ZeroDivisionError("denominator must not be zero")
    sign = 1 if numerator >= 0 else -1
    return sign * ((abs(numerator) + denominator // 2) // denominator)


def compute_player_stats(player_id: int, records: list[SessionRecord]) -> PlayerStats:
    """Derive a player's statistics from completed-session records."""
    ordered = sorted(records, key=lambda record: (record.session.ended_at or "", record.session.id))
    session_nets: list[int] = []
    rounds_won = rounds_lost = 0
    total_round_won = total_round_lost = 0
    best_round_win: int | None = None
    worst_round_loss: int | None = None
    for record in ordered:
        if player_id not in record.player_ids:
            continue
        net = 0
        for round_ in record.rounds:
            for participant in round_.participants:
                if participant.player_id != player_id:
                    continue
                if participant.role == "winner":
                    net += participant.amount_cents
                    rounds_won += 1
                    total_round_won += participant.amount_cents
                    if best_round_win is None or participant.amount_cents > best_round_win:
                        best_round_win = participant.amount_cents
                else:
                    net -= participant.amount_cents
                    rounds_lost += 1
                    total_round_lost += participant.amount_cents
                    if worst_round_loss is None or participant.amount_cents > worst_round_loss:
                        worst_round_loss = participant.amount_cents
        session_nets.append(net)

    sessions_played = len(session_nets)
    profitable = sum(1 for net in session_nets if net > 0)
    losing = sum(1 for net in session_nets if net < 0)
    if sessions_played:
        ordered_nets = sorted(session_nets)
        middle = sessions_played // 2
        if sessions_played % 2:
            median = ordered_nets[middle]
        else:
            median = round_div(ordered_nets[middle - 1] + ordered_nets[middle], 2)
        best_session: int | None = max(session_nets)
        worst_session: int | None = min(session_nets)
    else:
        median = 0
        best_session = None
        worst_session = None

    longest_win = longest_loss = current_win = current_loss = 0
    for net in session_nets:
        if net > 0:
            current_win += 1
            current_loss = 0
        elif net < 0:
            current_loss += 1
            current_win = 0
        else:
            current_win = current_loss = 0
        longest_win = max(longest_win, current_win)
        longest_loss = max(longest_loss, current_loss)

    rounds_played = rounds_won + rounds_lost
    return PlayerStats(
        player_id=player_id,
        sessions_played=sessions_played,
        total_net_cents=sum(session_nets),
        total_won_cents=sum(net for net in session_nets if net > 0),
        total_lost_cents=sum(-net for net in session_nets if net < 0),
        profitable_sessions=profitable,
        losing_sessions=losing,
        break_even_sessions=sessions_played - profitable - losing,
        rounds_played=rounds_played,
        rounds_won=rounds_won,
        rounds_lost=rounds_lost,
        total_round_won_cents=total_round_won,
        total_round_lost_cents=total_round_lost,
        average_session_cents=round_div(sum(session_nets), sessions_played)
        if sessions_played
        else 0,
        median_session_cents=median,
        best_session_cents=best_session,
        worst_session_cents=worst_session,
        best_round_win_cents=best_round_win,
        worst_round_loss_cents=worst_round_loss,
        average_winning_round_cents=round_div(total_round_won, rounds_won) if rounds_won else None,
        average_losing_round_cents=round_div(total_round_lost, rounds_lost)
        if rounds_lost
        else None,
        longest_winning_streak=longest_win,
        longest_losing_streak=longest_loss,
    )
