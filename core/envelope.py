"""Public source envelope: untrusted input -> trusted Observation.

Border validator. The core never sees source-specific fields (no composer,
human presence, versions, URLs, or any chat-service vocabulary): unknown
fields are accepted and ignored so sources can evolve without breaking the
contract. Only {"generating", "finished", "texts"} leave this function.

Limits (documented, fail-closed): at most MAX_TEXTS texts, each at most
MAX_TEXT_LEN characters. Anything else invalid raises ValidationError with a
short generic message (no internals leak).
"""
from collections.abc import Mapping

MAX_TEXTS = 500
MAX_TEXT_LEN = 100_000


class ValidationError(ValueError):
    """Controlled validation failure. Message is safe to expose."""


def validate(envelope):
    """Validate a public envelope. Returns {"generating", "finished", "texts"}.

    generating/finished: optional, default False, must be bool when present.
    texts: required list of strings. Unknown fields are ignored.
    """
    if not isinstance(envelope, Mapping):
        raise ValidationError("envelope must be a mapping")
    generating = envelope.get("generating", False)
    if not isinstance(generating, bool):
        raise ValidationError("generating must be a boolean")
    finished = envelope.get("finished", False)
    if not isinstance(finished, bool):
        raise ValidationError("finished must be a boolean")
    if "texts" not in envelope:
        raise ValidationError("texts is required")
    texts = envelope["texts"]
    if not isinstance(texts, list):
        raise ValidationError("texts must be a list")
    if len(texts) > MAX_TEXTS:
        raise ValidationError(f"texts exceeds {MAX_TEXTS} items")
    for item in texts:
        if not isinstance(item, str):
            raise ValidationError("texts items must be strings")
        if len(item) > MAX_TEXT_LEN:
            raise ValidationError(f"text exceeds {MAX_TEXT_LEN} characters")
    return {"generating": generating, "finished": finished,
            "texts": list(texts)}
