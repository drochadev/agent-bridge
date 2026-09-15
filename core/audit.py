"""AuditSink contract: observability that can never break delivery.

Rule: any exception raised by a sink is swallowed by the emitter.
Sinks with I/O (file, database) belong in adapters/.
"""
from typing import List, Protocol, Tuple, runtime_checkable


@runtime_checkable
class AuditSink(Protocol):
    """Minimum contract."""

    def record(self, event: str, detail: str = "") -> None:
        ...


class MemoryAuditSink:
    """In-memory sink for tests and demos."""

    def __init__(self):
        self.events: List[Tuple[str, str]] = []

    def record(self, event: str, detail: str = "") -> None:
        self.events.append((event, detail))

    def of(self, event: str) -> List[str]:
        return [detail for name, detail in self.events if name == event]


class NullAuditSink:
    """Sink that discards everything."""

    def record(self, event: str, detail: str = "") -> None:
        pass
