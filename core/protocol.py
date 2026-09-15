"""Minimal public message protocol: extract, identify, hash.

Message contract (plain dict, no Message class):
  {id, body, origin} — all strings. "origin" is opaque and always supplied by
  the calling adapter (it names the structural source, never the content).

Canonical block form (public, direction-free):
  [MSG]
  ...body...
  [/MSG]
The opening tag must start a line; the closing tag is REQUIRED — an
unclosed block produces no block (None). Only the first block travels; text
outside the block never travels. Code fences (```...```) are removed before
parsing so quoted examples are never treated as blocks.
"""
import hashlib
import re
import uuid

_OPEN = re.compile(r"^\[MSG\][ \t]*\r?\n?", re.M)
_CLOSE = re.compile(r"^\[/MSG\]", re.M)
_FENCE = re.compile(r"```.*?```", re.S)


def _without_fences(text):
    return _FENCE.sub("", text or "")


def extract_block(text):
    """Return the first canonical block body, stripped, or None.

    A block without its closing tag is not a block (returns None).
    Knows nothing about directions, agents, or private systems.
    """
    clean = _without_fences(text)
    opening = _OPEN.search(clean)
    if not opening:
        return None
    rest = clean[opening.end():]
    closing = _CLOSE.search(rest)
    if not closing:
        return None
    body = rest[:closing.start()].strip()
    return body or None


def make_id():
    """Generate a public message id. No database, no external state."""
    return "msg_" + uuid.uuid4().hex[:12]


def content_hash(body):
    """SHA-256 of the exact string given (callers hash the stripped body)."""
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def contains_reserved_marker(text, markers=()):
    """True if any caller-supplied reserved substring is present.

    The marker list is owned by the caller and empty by default. This function
    states a fact; it defines no drop policy.
    """
    return any(m and m in (text or "") for m in markers)
