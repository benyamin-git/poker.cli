"""Domain errors raised by the core and repository layers."""

from __future__ import annotations


class PokerError(Exception):
    """Base class for all expected poker.cli errors."""


class NotFoundError(PokerError):
    """A requested record does not exist."""


class ValidationError(PokerError):
    """User input violates an accounting or format rule."""


class StateError(PokerError):
    """The command is not valid for the current application state."""


class ConflictError(PokerError):
    """The change conflicts with existing data."""
