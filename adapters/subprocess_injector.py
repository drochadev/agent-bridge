"""Subprocess injector: deliver text to a new local process via stdin.

One process per delivery, argv only (never a shell string), communicate() for
deadlock-free writing. Success = the input was accepted without raising; a
non-zero exit code alone is NOT a failure (proof belongs to a Prover).
Timeout kills the process and raises; missing executables and broken pipes
propagate as OSError. No retry, no logging, no audit, no proof, no knowledge
of deliveries, flows, lifecycles, agents, or window systems.

Known stdlib boundary (documented, not worked around): communicate()
absorbs EPIPE when the child exits before reading, so an early-exiting child
is indistinguishable from success at this layer. Genuine delivery failure
detection belongs to a Prover, never to this injector.

Precondition (enforced upstream by Delivery.put, not duplicated here):
text is a non-empty string.
"""
import subprocess

_DEVNULL = subprocess.DEVNULL


class SubprocessInjector:
    """argv: non-empty sequence of program arguments (no shell)."""

    def __init__(self, argv, *, timeout_s=10, encoding="utf-8"):
        if isinstance(argv, (str, bytes)) or not argv:
            raise ValueError("argv must be a non-empty sequence of arguments")
        items = list(argv)
        if any(not isinstance(a, str) for a in items):
            raise ValueError("argv items must be strings")
        self._argv = items
        self._timeout_s = timeout_s
        self._encoding = encoding

    def __call__(self, text):
        proc = subprocess.Popen(
            list(self._argv),
            stdin=subprocess.PIPE,
            stdout=_DEVNULL,
            stderr=_DEVNULL,
            shell=False,
        )
        try:
            proc.communicate(text.encode(self._encoding),
                             timeout=self._timeout_s)
        except BaseException:
            proc.kill()
            proc.wait()
            raise
        return None  # success = no exception; exit code intentionally ignored
