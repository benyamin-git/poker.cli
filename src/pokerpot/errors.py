"""Domain errors raised by the core and repository layers."""

from __future__ import annotations


class PokerPotError(Exception):
    """Base class for all expected PokerPot errors."""


class NotFoundError(PokerPotError):
    """A requested record does not exist."""


class ValidationError(PokerPotError):
    """User input violates an accounting or format rule."""


class StateError(PokerPotError):
    """The command is not valid for the current application state."""


class ConflictError(PokerPotError):
    """The change conflicts with existing data."""
