"""Convenience one-shot policies built on top of put()/take()/settle().

Policies, not required parts of the abstraction: they never presume success
and delegate every decision to the delivery slot, the injector and the prover.
"""
from typing import Tuple

from core.delivery import ACCEPTED, DELIVERED, DROPPED
from core.transport import Injector, Prover

EMPTY = "empty"


def attempt_once(delivery, text: str, inject: Injector,
                 prove: Prover) -> Tuple[str, str]:
    """put -> take -> inject -> prove in one call."""
    status, detail = delivery.put(text)
    if status != ACCEPTED:
        return status, detail
    item = delivery.take()
    if item is None:
        # take() already audited the drop (gate closed between put and take)
        return DROPPED, "gate-closed-at-take"
    try:
        inject(item)
    except Exception as exc:
        return delivery.settle(item["id"], DROPPED,
                               f"inject-failed: {type(exc).__name__}")
    try:
        proven = prove(item)
    except Exception as exc:
        return delivery.settle(item["id"], DROPPED,
                               f"prove-failed: {type(exc).__name__}")
    if not proven:
        return delivery.settle(item["id"], DROPPED, "unproven")
    return delivery.settle(item["id"], DELIVERED)


def take_attempt(delivery, inject: Injector,
                 prove: Prover) -> Tuple[str, object]:
    """Take one pending item and attempt it: take -> inject -> prove -> settle.

    Empty slot returns ("empty", None) with no audit event. Note: take()
    also reports None when the gate drops at take time (audited inside
    take()); take_attempt honestly surfaces both as "empty" — check the
    audit sink when the distinction matters. Transport exceptions are
    settled as drops, never propagated. Settle semantics (late/wrong-id
    rejection) belong to Delivery and are preserved verbatim.
    """
    item = delivery.take()
    if item is None:
        return EMPTY, None
    try:
        inject(item)
    except Exception as exc:
        return delivery.settle(item["id"], DROPPED,
                               f"inject-failed: {type(exc).__name__}")
    try:
        proven = prove(item)
    except Exception as exc:
        return delivery.settle(item["id"], DROPPED,
                               f"prove-failed: {type(exc).__name__}")
    if not proven:
        return delivery.settle(item["id"], DROPPED, "unproven")
    return delivery.settle(item["id"], DELIVERED)
