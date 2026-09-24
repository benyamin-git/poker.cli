# PokerPot — Implementation Plan v2

This document is the source of truth for the project. It replaces an earlier
draft plan that has been deleted.

## 1. What we're building

A CLI-only ledger for poker-night money: record rounds (who lost what, who won
the pot), derive balances, settlement, history and accounting stats. Local
SQLite, no server, no network, runs in Termux and on desktop Linux. Python
3.11+, `typer` + `rich`, integer cents only.

## 2. Decisions

- **Stack:** Typer + Rich, Python >=3.11, src-layout package, `pytest`, MIT,
  pip-installable.
- **Splitting:** equal split by default; optional explicit per-winner amounts
  (side pots), validated to balance.
- **Roster:** add players anytime (including inline during round entry); remove
  only if they have no rounds in that session.
- **Players:** rename allowed (history follows the player ID); delete only if no
  round references exist.
- **After end:** `session reopen` only; no delete command.
- **Undo:** last round of the active session only.
- **Round entry:** interactive prompts *and* non-interactive flags.
- **Currency:** display fixed `$`; internal integer cents.
- **Stats:** completed sessions only; break-even counts in win-rate denominator
  and resets streaks.
- **Commits:** one commit per stage, conventional messages.
- **Local dev:** gitignored `.venv` (`python3 -m venv --without-pip` + official
  `get-pip.py`), then `pip install -e '.[dev]'` (typer, rich, pytest, ruff).

## 3. Explicit choices beyond the draft

1. **Single active session at a time**, enforced by a partial unique index.
   `session start` refuses if one is active.
2. **No `session delete`** — corrections go through `session reopen`; history is
   never destructed.
3. **`session export <id>`** is canonical (instead of top-level `export`);
   `history` stays a read-only list.
4. **Text export is ANSI-free by default** so it pastes cleanly into
   Telegram/WhatsApp; Rich colors are for interactive commands only.
5. **Custom winner amounts** for side pots. Default flow is still equal split.
6. **Stats only from completed sessions.**
7. **Docs/tests use generic names** (Alice/Bob/Carol/Dave).
8. **Ruff** as a dev-only dependency.

## 4. Assumptions

- Amount input: `20`, `20.5`, `$20.50` mean dollars; exactly <=2 decimals;
  zero/negative rejected; display always `$20.50` / `-$20.50`, no thousands
  separators.
- Equal-split remainder: `pot % winners` extra cents go to winners **in the
  order entered**; documented in README.
- Pot must be at least 1 cent per winner.
- Greedy settlement (largest debtor vs largest creditor, ties by player ID).
  Deterministic; *not* guaranteed globally minimal (that's NP-hard) —
  documented honestly.
- Timestamps stored UTC ISO-8601, displayed in local time. Default session name
  is the local `Session YYYY-MM-DD HH:MM`.
- DB at `$XDG_DATA_HOME/pokerpot/pokerpot.db`, falling back to
  `~/.local/share/pokerpot/pokerpot.db`; override via `--db` / `POKERPOT_DB`.
- Averages/medians are rounded half-away-from-zero to the nearest cent;
  documented.
- `player show` / `stats` accept a name (case-insensitive) or numeric ID.
- LICENSE copyright line: `Benyamin` (no email). `pyproject` has no email.
- `plan.md` is committed with the scaffold.

## 5. Layout & tooling

```
pyproject.toml            # hatchling, console script pokerpot, deps typer/rich
README.md  LICENSE  .gitignore  plan.md
src/pokerpot/
  __init__.py  __main__.py  cli.py        # thin Typer layer
  db.py        repo.py                    # connection+migrations; typed queries
  accounting.py settlement.py stats.py    # pure engine, no CLI imports
  money.py     export.py     render.py    # cents; text/json/csv; Rich tables
  errors.py
tests/  test_money, test_accounting, test_settlement, test_stats, test_db, test_cli
```

`python -m pokerpot` also works. The engine is CLI-independent and fully
unit-tested.

## 6. Schema (migration v1, `PRAGMA user_version`)

- `players(id, name UNIQUE COLLATE NOCASE, created_at)`
- `sessions(id, name, status active|completed, started_at, ended_at)` plus a
  partial unique index enforcing one `active` row
- `session_players(session_id, player_id, PK both)` — cascade on session/player
  delete
- `rounds(id, session_id, number, created_at, UNIQUE(session_id, number))`
- `round_participants(id, round_id, player_id, role winner|loser,
  amount_cents CHECK > 0, UNIQUE(round_id, player_id))` — `ON DELETE RESTRICT`
  on player
- Foreign keys on; indexes on rounds.session_id and participants
  round_id/player_id.

The ledger (`rounds` + `round_participants`) is the only source of truth;
balances, settlement and stats are always recomputed.

## 7. Accounting rules

- `parse_money` via `Decimal`, converted exactly to int cents; floats never
  used.
- Round validation: >=1 loser, >=1 winner, no player in both roles, no
  duplicates, all in the session roster, amounts > 0,
  `sum(losers) == sum(winners)`.
- Equal split: `share, rem = divmod(pot, n)`; first `rem` winners get
  `share + 1`.
- Custom split: every winner > 0, sum must equal pot exactly.
- Inserting a round is one transaction (validate, then insert round +
  participants). The UI previews per-player deltas before confirm.
- Invariants asserted in tests: per-round losses == winnings; per-session
  balances sum to $0.

## 8. Settlement

Greedy matching of debtors/creditors, deterministic ordering, zero-net players
produce no transfers. Shown on `session end`, previewable with
`session show --settlement`.

## 9. CLI surface

```
pokerpot [--db PATH] --version
player add NAME | list | show NAME|ID | rename OLD NEW | delete NAME|ID
session start [--name N] [--players a,b,c] | list | show [ID] [--rounds] [--settlement]
session add-player NAME | remove-player NAME|ID | end [ID] [--yes] | reopen ID
session export [ID] [--format text|json|csv] [--output FILE]
round                     # interactive: loser(s) -> amount(s) -> pot -> winner(s) -> split -> confirm
round add [--loser NAME=AMT]... [--winner NAME[=AMT]]... [--yes]
round list | undo [--yes]
history
stats [PLAYER]
```

Interactive player pickers accept numbers, names and comma lists; unknown names
during round entry prompt to create and add. Errors are clear, actionable, and
never partially write.

## 10. Statistics (completed sessions only)

Sessions played, net total, total won/lost (sums of positive/negative session
nets), profitable/losing/break-even counts, session win rate = profitable /
played (break-even in denominator), rounds participated/won/lost, round win
rate, average and median session result, best/worst session, best single-round
win, worst single-round loss, average winning/losing round, longest win/loss
streak (break-even resets). No ROI/EV/VPIP/skill metrics; README states these
are accounting stats, not poker-skill stats.

## 11. Exports

- **text** (default): plain, verification-friendly — header, players, every
  round with losers/winners, final standings, settlement, loss/win totals check.
- **json**: full structured session with `schema_version`.
- **csv**: long format `round,player,role,amount_cents,amount`.
- `--output FILE` optional; everything offline.

## 12. Testing

Engine unit tests: basic/multi-loser/multi-winner rounds, uneven cent split and
deterministic remainder, custom split validation, multi-round accumulation,
settlement combinations including zero balances, invariant sums. Plus money
parsing/formatting edge cases, DB migration/idempotency and constraints, stats
definitions (including median/rounding/streaks), and a CliRunner end-to-end
happy path (start -> rounds -> end -> export) against a temp DB.

## 13. Stages & commits

- **Stage 0** — delete original `plan.md`, write this plan, scaffold
  `pyproject`/LICENSE/`.gitignore`/package skeleton/venv.
  Commit `chore: scaffold project and reviewed plan`.
- **Stage 1** — DB + migrations + `player *`.
  Commit `feat: players and database layer`.
- **Stage 2** — `session *` lifecycle + roster.
  Commit `feat: poker sessions and rosters`.
- **Stage 3** — round engine + interactive/flag entry + undo.
  Commit `feat: round recording and undo`.
- **Stage 4** — balances + settlement + end-of-session report.
  Commit `feat: balances and settlement`.
- **Stage 5** — history + text/json/csv exports.
  Commit `feat: history and exports`.
- **Stage 6** — `stats`. Commit `feat: player statistics`.
- **Stage 7** — full README, error-message polish, coverage pass.
  Commit `docs: complete README and polish`.

Each stage ends with `pytest -q`, `ruff check` and a manual CLI smoke run; no
half-working states between commits.
