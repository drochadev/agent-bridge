"""Convenience one-shot policy built on top of put()/take().

A policy, not a required part of the abstraction: it never presumes success
and delegates every decision to the delivery slot, the injector and the prover.
"""
from typing import Tuple

from core.delivery import ACCEPTED, DELIVERED, DROPPED
from core.transport import Injector, Prover


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
