"""Observation adapter (source -> finished text): validate + stability only.

Composition, not logic: each envelope goes through core.envelope.validate,
then into a StabilityDetector. None means "no finished message yet"; a str
means "a message is ready for the next stage". No transport here, no I/O, no
knowledge of DOM, browsers, HTTP, agents, or processes.
"""
from core.envelope import validate
from core.stability import StabilityDetector


class ObservationFeed:
    """Stateful feed: the detector needs history across observations."""

    def __init__(self):
        self._detector = StabilityDetector()

    def observe(self, envelope):
        """Validate and feed one envelope. Returns str | None.

        Invalid envelopes raise ValidationError (controlled, from validate).
        """
        observation = validate(envelope)
        result = self._detector.observe(
            observation["generating"], observation["finished"],
            observation["texts"])
        if result is None:
            return None
        return result["text"]
