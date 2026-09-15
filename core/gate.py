"""Gate contract: decides whether delivery may proceed, at put AND take time."""
from typing import Protocol, runtime_checkable, Tuple


@runtime_checkable
class Gate(Protocol):
    """Minimum contract. Returns (open, reason)."""

    def is_open(self) -> Tuple[bool, str]:
        ...


class ManualGate:
    """Simple controllable gate for embedding code and tests."""

    def __init__(self, open_: bool = True, reason: str = ""):
        self._open = open_
        self._reason = reason

    def set(self, open_: bool, reason: str = "") -> None:
        self._open = open_
        self._reason = reason

    def is_open(self) -> Tuple[bool, str]:
        return self._open, self._reason
