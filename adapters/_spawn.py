"""Shared subprocess primitive for adapters (no shell, no retry, no audit).

Not a public contract: a small helper so adapters do not duplicate Popen
plumbing. Callers own timeouts, encodings and what stdin/stdout mean.
"""
import subprocess


def run(argv, data, timeout_s, capture=False):
    """Spawn argv, feed data to stdin, optionally capture stdout.

    Returns captured stdout bytes (or b"" when not capturing). Timeout kills
    and raises; spawn failures propagate as OSError. Exit code is the
    caller's business and is never checked here.
    """
    proc = subprocess.Popen(
        list(argv),
        stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        shell=False,
    )
    try:
        out, _ = proc.communicate(data, timeout=timeout_s)
    except BaseException:
        proc.kill()
        proc.wait()
        raise
    return out or b""
