"""Transport protocols: the only way the core touches the outside world.

Concrete implementations (subprocess, HTTP, files, windows) belong in
adapters/ and are created only when a real use case needs them.
"""
from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class Injector(Protocol):
    """Delivers an item. Success = returns without raising.

    The return value is ignored and never interpreted as success/failure.
    """

    def __call__(self, item: Dict[str, Any]) -> Any:
        ...


@runtime_checkable
class Prover(Protocol):
    """Confirms a delivery. Truthy result = proven."""

    def __call__(self, item: Dict[str, Any]) -> Any:
        ...
