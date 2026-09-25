# poker.cli

A CLI-only ledger for poker-night money between friends.

poker.cli records one thing: **who lost how much and who won the resulting
pot**. From that ledger it derives session balances, a simplified settlement,
full history and honest accounting statistics. Everything is stored locally in
a single SQLite file. No accounts, no server, no network, no TUI.

Designed to run natively in [Termux](https://termux.dev) on Android as well as
on any normal Linux system.

## Why

Settling up after a poker night is usually a group-chat argument: someone
half-remembers who owes what. poker.cli keeps a verifiable ledger. At the end of
the night it prints final standings and a short list of transfers that settles
everyone, and it can export the whole session so friends can independently
check that the numbers are not arbitrary.

## Features

- Persistent players reused across sessions.
- One active session at a time, with optional rounds and a settlement preview.
- Fast interactive round entry, plus non-interactive flags for scripting.
- Equal pot splits by default; explicit per-winner amounts for side pots.
- Balances and settlement always derived from recorded rounds.
- Full session history, `session reopen` for corrections, last-round undo.
- Human-readable text reports plus JSON and CSV exports.
- Accounting statistics per player (results, not poker skill).
- Integer cents everywhere; never floating point.
- Single local SQLite file, easy to back up.
- Zero runtime network access.

## Requirements

- Python 3.11 or newer.

## Installation

With [pipx](https://pipx.pypa.io) (recommended, keeps the CLI isolated):

```sh
pipx install .
```

Or with pip:

```sh
python3 -m pip install .
```

This installs a `poker` command. You can also run it without installing:
`python3 -m poker --help`.

### Termux

```sh
pkg install python git
git clone https://github.com/benyamin-git/poker.cli
cd poker.cli
pip install .
poker --help
```

All dependencies are pure Python, so no compiler is needed.

## Quick start

```sh
poker player add Alice
poker player add Bob
poker player add Carol

poker session start --name "Friday Poker" --players Alice,Bob,Carol
# or run 'poker session start' for an interactive player picker

# Interactive round entry:
poker round

# Or scriptable entry: NAME=AMOUNT for losers, NAME (or NAME=AMOUNT) for winners
poker round add --loser Alice=20 --winner Bob
poker round add --loser Bob=30 --loser Carol=10 --winner Alice
poker round add --loser Alice=50 --winner Bob=30 --winner Carol=20

poker session show            # current balances
poker session show --rounds   # add the round-by-round ledger
poker round undo              # remove the most recent round

poker session end             # final standings + settlement
```

Later:

```sh
poker history
poker stats
poker stats Bob
poker session show 1 --settlement
poker session export 1
```

Run `poker --help` or `poker <command> --help` for every option.

## How a round works

A round has one or more losers and one or more winners. The losers' amounts
form the pot; the winners receive it. poker.cli refuses to record a round unless
the losses and winnings balance exactly:

```text
Round 3
  Alice  -$20.00
  Carol  -$30.00
  Bob    +$30.00
  Dave   +$20.00
  Pot: $50.00
```

### Splitting rules

- **Equal split (default):** the pot is divided equally. When it does not
  divide evenly into cents, the first winners *in the order you entered them*
  receive one extra cent each. Example: a $10.00 pot with three winners becomes
  `$3.34`, `$3.33`, `$3.33`.
- **Custom amounts:** with multiple winners you can enter each winner's amount
  explicitly (for side pots). The amounts must be positive and add up to the
  pot exactly.
- The pot must be at least 1 cent per winner.

## Settlement

Final balances always sum to $0. Player balances are derived only from the
recorded rounds; debts are never recorded separately.

The settlement is produced by a deterministic greedy algorithm: the largest
debtor pays the largest creditor until everyone is square, with ties broken by
player ID. This keeps the number of transfers small, but it is not guaranteed
to be the mathematically smallest possible set (finding that is NP-hard). The
settlement is shown by `poker session end`, can be previewed mid-session
with `poker session show --settlement`, and is included in every export.

```text
Settlement
  Alice -> Ben   $45.00
  Alice -> Carol $35.00
```

## Session rules

- Only one session is active at a time.
- Players can be added to an active session at any time (including from inside
  round entry); they can be removed only if they have no rounds in that
  session.
- `poker round undo` removes the most recent round of the active session.
- Completed sessions are historical records: `poker session reopen <id>`
  flips one back to active for corrections, then end it again. There is no
  delete command.
- Players keep their identity (and history) when renamed. A player can be
  deleted only if they have no recorded rounds.

## Data location and backup

The database lives at:

```text
$XDG_DATA_HOME/poker.cli/poker.db
```

falling back to `~/.local/share/poker.cli/poker.db`. The file is created
automatically on first run.

- Use another database with `--db PATH` or the `POKER_DB` environment
  variable.
- **Backup:** copy the single `.db` file. That is the entire state.
- Everything is offline; poker.cli never makes network requests.

## Exports

```sh
poker session export            # active session as a plain-text report
poker session export 1          # a completed session by ID
poker session export 1 -f json  # machine-readable JSON
poker session export 1 -f csv   # long-format ledger rows
poker session export 1 -o report.txt
```

- **text** (default): plain text with no colors or escape codes, ready to paste
  into Telegram, WhatsApp, Discord, etc. It lists every round, final standings,
  the settlement and a balance check so friends can verify the numbers.
- **json:** the full session (metadata, players, rounds, standings, settlement)
  with a `schema_version` field.
- **csv:** one row per round participant:
  `round,player,role,amount_cents,amount`.

## Statistics

`poker stats` prints a summary for every player; `poker stats NAME`
prints full details. Only **completed** sessions are counted.

poker.cli only knows money movements. These are *accounting* statistics, not
poker-skill statistics. It does not (and cannot) compute ROI, EV, VPIP,
aggression, win probability or anything that would require cards, hands,
blinds or betting decisions. Nothing is collected that could support those
claims.

Definitions used:

| Statistic | Definition |
| --- | --- |
| Sessions played | Completed sessions the player was part of. |
| Total net | Sum of the player's session nets. |
| Total won / lost | Sum of positive / absolute negative session nets. |
| Profitable / losing / break-even session | Session net > 0 / < 0 / = 0. |
| Session win rate | Profitable sessions ÷ sessions played (break-even counts in the denominator). |
| Rounds played | Rounds where the player appeared as a loser or winner. |
| Rounds won / lost | Participant rows with role winner / loser. |
| Round win rate | Rounds won ÷ rounds played. |
| Average / median session | Computed over session nets. |
| Best / worst session | Highest / lowest session net. |
| Best single-round win / worst single-round loss | Largest amount won / lost in one round. |
| Average winning / losing round | Total won ÷ rounds won, total lost ÷ rounds lost. |
| Longest winning / losing streak | Consecutive profitable / losing sessions in chronological order; a break-even session resets the streak. |

Averages and medians are exact integer-cent computations rounded half away
from zero to the nearest cent.

## Error handling

poker.cli never silently accepts invalid financial data. Examples of rejected
input: negative or zero amounts, malformed amounts, unbalanced pots, a player
in both roles of one round, players outside the session, duplicate players,
operations on an ended session, invalid IDs and attempts to delete history.
Errors are printed to stderr with a non-zero exit code, and a round is only
written after all validation passes.

## Development

```sh
git clone https://github.com/benyamin-git/poker.cli
cd poker.cli
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest            # test suite
.venv/bin/ruff check .      # lint
.venv/bin/ruff format .     # format
```

The accounting engine (`src/poker/accounting.py`), settlement
(`settlement.py`) and statistics (`stats.py`) are pure functions with no
database or CLI dependencies, so they are easy to test in isolation. The
database layer lives in `db.py` and `repo.py`; all terminal output is
centralized in `render.py` and `prompts.py`.

## License

[LICENSE](LICENSE).
